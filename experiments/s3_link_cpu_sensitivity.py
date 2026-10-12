"""API-active CPU sensitivity and all T mode periods; not WCET or adoption.

Keep the recorded 200 cycles/page ledger intact. A separate scenario replaces
that term with an explicit API invocation count and active time. RF/FFT kernel
costs, IRQ, CRC, scheduler and whole FPGA resources remain unverified.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = 4096
CPU_MHZ = 240
CPU_TOTAL_MCYCLES = 480
RF_LOW_HIGH_MCYCLES = (368.4375, 448.4375)


def active_cycles(active_us):
    if not math.isfinite(active_us) or active_us < 0:
        raise ValueError("API active time must be finite and nonnegative")
    return CPU_MHZ * active_us


def octal_time(pages):
    # Independently match the pinned 80-bit header, .25-us segment and API model.
    return pages * (PAGE / 80 + 80 / 640 + .25) + 20


def t_modes():
    records = []
    for mode, points in enumerate((2048, 4096, 8192), 1):
        period = points * 1008 / 8192 * 33 / 32
        pages = points * 4 // PAGE
        rf_apis = 40e6 / (3 * PAGE)
        frame_apis = (pages + 1) * 1e6 / period
        duty = 40 * octal_time(3) / (3 * PAGE) + octal_time(pages) / period
        records.append({
            "mode": mode, "FFT_points": points, "GI_1_32_period_us": period,
            "FFT_each_direction_MBps": points * 4 / period,
            "fixed_octal_time_utilization": duty,
            "fixed_octal_average_time_condition_pass": duty <= 1,
            "API_invocations_per_s_floor": rf_apis + frame_apis,
            "API_CPU_Mcycles_s_if_20us_active": (rf_apis + frame_apis) * 4800 / 1e6,
            "scope": "raw only on Octal; one complete FFT reply API/symbol; Quad input one API/page",
            "all_mode_routes_rejected": False, "CPU_WCET_verified": False,
        })
    return records


def rs_allocation(spec, route, assignment, caps, batch_s, rate, gap, active_us):
    names = route["ports"]
    residual = [caps[n][f"effective_gap{gap}_MBps"] * (1 - used)
                if caps[n]["kind"] in ("half", "down") else 0
                for n, used in zip(names, assignment["RPC_time_fractions"])]
    # Octal's three-page RF batch has the lowest API count per byte. This
    # minimizes only the average invocation count, not latency or CPU WCET.
    order = sorted(range(len(names)), key=lambda i: (0 if "Octal" in names[i] else 1, i))
    rf = [0.] * len(names)
    need = 100.
    for i in order:
        rf[i] = min(need, residual[i])
        need -= rf[i]
    if need > 1e-7:
        raise ValueError("RPC residual cannot carry the native RF stream")
    rf_calls = sum(b * 1e6 / (PAGE * (3 if "Octal" in n else 1)) for n, b in zip(names, rf))
    rpc_calls = sum((1 if "Octal" in n else msg["pages"]) / batch_s
                    for msg, n in zip(spec["records"], assignment["message_ports"]))
    calls = rf_calls + rpc_calls
    mc = calls * active_cycles(active_us) / 1e6
    return {
        "ports": names, "message_ports": assignment["message_ports"],
        "RF_MBps_allocation": rf, "RF_remaining_port_MBps": residual,
        "RF_margin_MBps": assignment["RF_margin_MBps"],
        "RF_API_invocations_per_s_floor": rf_calls,
        "RPC_API_invocations_per_s": rpc_calls,
        "API_CPU_Mcycles_s": mc,
        "RF_plus_API_low_high_CPU_percent": [(v + mc) / CPU_TOTAL_MCYCLES * 100 for v in RF_LOW_HIGH_MCYCLES],
        "solver_remaining_cycles_per_CW_low_high": [(CPU_TOTAL_MCYCLES - v - mc) * 1e6 / rate for v in RF_LOW_HIGH_MCYCLES],
        "same_batch_deadlines_verified": False, "CPU_WCET_verified": False,
        "whole_FPGA_resources": None, "performance_pass": None, "adopted": False,
    }


def calculate(audit, api_active_us=20):
    active_cycles(api_active_us)
    caps = {p["name"]: p for p in audit["profiles"]}
    rate = audit["rates"]["RS_codewords_s"]
    batch_s = audit["rates"]["RS_batch_us"] * 1e-6
    route_api = {}
    for key, catalog in audit["route_catalogs"].items():
        route_api[key] = {}
        for gap in (0, 8):
            entries = []
            for route in catalog[f"gap{gap}"]:
                calls = sum((p["down_MBps"] + p["up_MBps"]) * 1e6 /
                            (PAGE * (3 if "Octal" in p["name"] else 1)) for p in route["links"])
                entries.append({"ports": route["ports"], "API_invocations_per_s_floor": calls,
                                "API_CPU_Mcycles_s": calls * active_cycles(api_active_us) / 1e6})
            route_api[key][f"gap{gap}"] = entries
    owners = []
    for row in audit["assignments"]:
        old_boundary = (row["required_down_MBps"] + row["required_up_MBps"]) * 200 / PAGE
        owners.append({"id": row["id"], "owners": row["owners"], "flows": row["flows"],
                       "legacy_CPU_low_high_Mcycles_s": row["CPU_low_high_Mcycles_s"],
                       "legacy_200_cycles_per_page_Mcycles_s": old_boundary,
                       "CPU_before_replacement_boundary_low_high_Mcycles_s": [v - old_boundary for v in row["CPU_low_high_Mcycles_s"]],
                       "route_catalog": row["route_catalog"], "whole_FPGA_resources": None,
                       "per_core_WCET": None, "performance_pass": None, "adopted": False})
    rs = {}
    for name, spec in audit["RS_subpartitions"].items():
        rs[name] = {}
        for gap in (0, 8):
            rs[name][f"gap{gap}"] = [rs_allocation(spec, route, a, caps, batch_s, rate, gap, api_active_us)
                                      for route in spec[f"communication_only_gap{gap}"] for a in route["assignments"]]
    modes = t_modes()
    ta = next(r for r in owners if r["id"] == "S3-T-004")
    api_ta = modes[2]["API_invocations_per_s_floor"] * active_cycles(api_active_us) / 1e6
    ta_percent = [(v + api_ta) / CPU_TOTAL_MCYCLES * 100
                  for v in ta["CPU_before_replacement_boundary_low_high_Mcycles_s"]]
    return {
        "scope": __doc__, "module": "ESP32-S3-WROOM-1U-N16R8",
        "API_active_us_scenario": api_active_us, "API_active_time_is_measured_bound": False,
        "T_modes": modes, "T_A_Mode3_fixed_route_CPU_low_high_percent": ta_percent,
        "ownerships": owners, "fluid_route_API_sensitivity": route_api, "RS_route_API_sensitivity": rs,
        "accounting": {
            "legacy": "200 cycles/page is retained in source; replace it, do not add it again",
            "RS_RF": "368.4375/448.4375 Mcycles/s excludes the old RF boundary charge",
            "wire_overhead": "20us API remains in pinned wire capacities independently of CPU active time",
            "rounding": "RF and fluid calls are average floors; frame/batch edge rounding, IRQ, CRC, RTOS and cache stalls omitted",
            "allocation": "New RS RF stripe minimizes average API count; source minimax wire stripe remains a separate witness",
        },
        "native_samples_preserved": True, "additional_software_decimation": False,
        "additional_software_requantization": False,
        "all_microarchitectures_or_custom_transports_exhausted": False,
        "performance_stage_completed": False, "receiver_adopted": False, "complete_estimate": False,
    }


def summary(result):
    groups = {}
    for name, scenarios in result["RS_route_API_sensitivity"].items():
        groups[name] = {}
        for gap, rows in scenarios.items():
            oq = [r for r in rows if r["ports"] == ["SPI2_Octal80", "SPI3_Quad80"]]
            groups[name][gap] = {"message_assignments": len(rows), "octal_quad_assignments": len(oq),
                "octal_quad_solver_low_cycles_range": [min(r["solver_remaining_cycles_per_CW_low_high"][0] for r in oq),
                                                       max(r["solver_remaining_cycles_per_CW_low_high"][0] for r in oq)] if oq else None}
    return {"module": result["module"], "API_active_us_scenario": result["API_active_us_scenario"],
            "ownerships": len(result["ownerships"]), "T_modes": result["T_modes"],
            "T_A_Mode3_fixed_route_CPU_low_high_percent": result["T_A_Mode3_fixed_route_CPU_low_high_percent"],
            "RS_groups": groups, "performance_stage_completed": False,
            "receiver_adopted": False, "complete_estimate": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "reports/s3-partition-audit/estimate.json.gz")
    parser.add_argument("--output", type=Path, default=ROOT / "build/s3-link-cpu-sensitivity")
    parser.add_argument("--api-active-us", type=float, default=20)
    args = parser.parse_args()
    result = calculate(json.loads(gzip.decompress(args.input.read_bytes())), args.api_active_us)
    args.output.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    output = args.output / "results.json.gz"
    output.write_bytes(gzip.compress(encoded, mtime=0))
    overview = summary(result)
    overview["input_sha256"] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    overview["results_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    (args.output / "summary.json").write_text(json.dumps(overview, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(overview, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

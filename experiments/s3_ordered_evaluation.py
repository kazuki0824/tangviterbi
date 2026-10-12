"""Ordered capacity/deadline review of the existing finite S3 stage catalogue.

Exploratory links are retained with their original bandwidth margins, but they
are not assigned before the whole performance gate passes. Unknown is distinct
from false. Partial-design failure never rejects every implementation of a split.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from s3_ordered_constraints import report as constraints
from s3_rf_schedule_closure import core_demand
from s3_link_cpu_sensitivity import t_modes
from s3_runtime_schedule import report as runtime_schedule

ROOT = Path(__file__).resolve().parents[1]


def adoption_gate(performance, paths, native_preserved=True):
    if not native_preserved:
        return {"assigned_routes": [], "adopted": False, "reason": "quality-changing transport rescue excluded"}
    if performance is not True:
        return {"assigned_routes": [], "adopted": False,
                "reason": "performance unknown" if performance is None else "declared performance condition failed"}
    return {"assigned_routes": paths, "adopted": bool(paths),
            "reason": "performance then nonempty routes" if paths else "no communication route"}


def calculate():
    path = ROOT / "reports/s3-partition-audit/estimate.json.gz"
    audit = json.loads(gzip.decompress(path.read_bytes()))
    rows = []
    for row in audit["assignments"]:
        catalog = audit["route_catalogs"].get(row["route_catalog"])
        rows.append({"id": row["id"], "standard": row["standard"], "owners": row["owners"],
                     "crossing_information": row["flows"],
                     "CPU_legacy_low_high_percent": row["CPU_low_high_percent"],
                     "stage_only_resources": row["stage_only_resources"],
                     "whole_FPGA_resources": None, "per_core_WCET": None,
                     "performance_pass": None,
                     "exploratory_route_catalog": row["route_catalog"],
                     "exploratory_route_counts": {f"gap{g}": (len(catalog[f"gap{g}"]) if catalog is not None else None) for g in (0, 8)},
                     **adoption_gate(None, [])})
    partial = []
    for p in sorted((ROOT / "reports/s3-direct-stream-evidence").glob("**/result.json")):
        x = json.loads(p.read_text())
        fmax = (x.get("fmax") or {}).get("bridge.clk", {}).get("achieved")
        u = x.get("utilization") or {}
        # Routed occupancy counts real LUT4s and ALUs once; the pack-only
        # optimistic FF-sharing lower bound is a different quantity.
        used = u.get("LUT4", {}).get("used", 0) + u.get("ALU", {}).get("used", 0)
        required = 2667 * audit["rates"]["RS_codewords_s"] / 1e6 if x["mode"] == "S-all-RS" else None
        partial.append({"evidence": str(p.relative_to(ROOT)), "mode": x["mode"], "seed": x.get("seed", 1),
                        "minimum_logic_sites": x["logic_site_audit"]["minimum_required_logic_sites"],
                        "routed_logic_sites": used or None,
                        "routed_logic_occupancy_percent": used * 100 / 8640 if used else None,
                        "BSRAM": u.get("BSRAM"), "DSP": u.get("MULT18X18"),
                        "core_fmax_MHz": fmax, "CAD_exit_code": x["CAD_exit_code"],
                        "full_RS_required_MHz": required,
                        "full_RS_cycle_budget_pass_at_reported_fmax": fmax >= required if fmax and required else None,
                        "whole_receiver": False, "absent": x["absent"]})
    core_profiles = [core_demand(mode=mode, pack_cycles=pack, fft_us=fft,
                                prepare_core=prep, api_core=api, control_core=ctrl)
                     for mode in ("T", "S") for pack in (4, 6, 8)
                     for fft in ((500, 513) if mode == "T" else (0,))
                     for prep in (0, 1) for api in (0, 1) for ctrl in (0, 1)]
    for profile in core_profiles:
        profile["affinity_matches_current_core0_capture_service"] = all(profile[k] == 0 for k in ("prepare_core", "api_core", "control_core"))
        profile["cross_core_service_migration_implemented"] = False
    board = constraints()
    return {
        "scope": __doc__, "stage_catalogue_input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "finite_scope": "T 8 whole stages (256) + S 6 whole stages (64); RS subpartitions separately in source",
        "preconditions": board, "ownerships": rows, "partial_FPGA_implementations": partial,
        "CPU_per_core_necessary_scenarios": core_profiles,
        "CPU_profiles_are_measured_bounds": False,
        "per_core_model_omissions": ["actual RF MMIO read/packing cost", "RPC/CRC/IRQ", "memory/cache/DMA contention", "RTOS/service and stage barrier overhead"],
        "T_shortest_GI_deadlines": t_modes(),
        "runtime32_all_modes":runtime_schedule(),
        "RF": {"bank_samples": 12288, "T_bank_us": 768, "S_bank_us": 307.2,
               "T_poll_lateness_limit_us": 125, "S_poll_lateness_limit_us": 50},
        "direct_bridge": {"page_bytes": 4096, "slots": 4, "bytes": 16384,
                          "at_90MHz_continuous_read_MBps_upper": 120,
                          "consumer_stalls_not_included_in_rate": True,
                          "S_100MBps_zero_service_stall_time_us_upper": 163.84,
                          "T_40MBps_zero_service_stall_time_us_upper": 409.6,
                          "credit_sender_implemented": True,
                          "credit_limit":3,
                          "credit_RTL":"rtl/s3_rf_credit.sv",
                          "credit_SDK_adapter":"experiments/s3_rf_pump.c",
                          "physical_credit_IO_verified":False,
                          "same_frame_latency_verified": False},
        "communication": {"catalogue": str(path.relative_to(ROOT)),
                          "all_existing_candidate_routes_and_margins_retained_in_source": True,
                          "profiles": audit["profiles"],
                          "assigned_routes_after_performance": [],
                          "performance_verified_candidates": 0,
                          "reason": "whole performance gate unresolved; route hypotheses are not adopted routes"},
        "fixed_TS_configuration": {"T_S_exclusive": True, "common_Octal_Quad_pin_witness": True,
                                   "same_S3_binary_SIMD_and_RS_SDK_union": "native-direct-phy-runtime32",
                                   "union_SDK_result_available": (ROOT / "reports/s3-mode-union-evidence/results.json").exists(),
                                   "union_SDK_profile_links_task_driver_adapters":True,
                                   "union_SDK_app_executes_runtime":False,
                                   "NOR_control_contract": "experiments/s3_mode_switch.c (C); experiments/s3_nor_images.py:Switch (model)",
                                   "actual_T_S_images": False, "physical_reconfiguration_test": False,
                                   "final_configuration_adopted": False},
        "performance_stage_completed": False, "receiver_adopted": False, "complete_estimate": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/s3-ordered-evaluation/results.json.gz")
    args = parser.parse_args()
    x = calculate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(), mtime=0))
    print(json.dumps({"ownerships": len(x["ownerships"]), "partial_FPGA_implementations": x["partial_FPGA_implementations"],
                      "performance_verified_candidates": 0, "receiver_adopted": False}, indent=2))

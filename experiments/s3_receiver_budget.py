#!/usr/bin/env python3
"""Finite route/budget enumeration for the two specified S3 ownerships.

These are conditional throughput/resource scenarios, not real-time proofs.
Inputs freeze the previous estimate's stage budgets; only measured FEC cells
and the explicitly corrected SRAM layout are substituted. Requires ortools.
"""
import argparse
import itertools
import json
import math
from pathlib import Path
from ortools.linear_solver import pywraplp

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = 4092


def profile(p):
    p = dict(p)
    cap = p["capacity_Bps"] / 1e6
    name = p["name"]
    command = (96 + 18 * math.ceil((PAYLOAD + 16) / 512)) / 40 if name.startswith("SDIO") else .3 if name.startswith("SPI") else 0
    gap = 2 if name.startswith(("SPI", "SDIO")) else 0
    p["service_us"] = (PAYLOAD + 16) / cap + command + gap
    p["effective_MBps"] = PAYLOAD / p["service_us"]
    return p


def enumerate_mode(mode, inputs, fec):
    st = mode["standard"]
    ports = [profile(p) for p in inputs["ports"]]
    flows = [dict(f, direction="down" if f["direction"] == "SoC→FPGA" else "up") for f in mode["flows"]]
    nonraw = sum(f["MBps"] for f in flows if f["source"] != "RF")
    event_cpu = sum(f["MBps"] for f in flows) * 200 / PAYLOAD
    total_cpu = mode["base_cpu_Mcycles_s"] + nonraw + event_cpu
    pinned = list(mode["pinned_Mcycles_s"])
    pinned[0] += nonraw + event_cpu
    cpu = max(total_cpu / 480, max(pinned) / 240)
    stage = {k: sum(s[k] for s in mode["stages"].values()) for k in inputs["capacity"]}
    stage["logic_sites_estimate"] += (fec["RS"]["logic_equivalents"] - 2085
                                      + fec["Viterbi"]["logic_equivalents"] - 2952)
    stage["FF"] += fec["RS"]["FF"] - 960 + fec["Viterbi"]["FF"] - 1502
    if st == "S":
        # Proposed S-only cycle reduction, NOT measured RTL. Explicitly charge
        # its controller/operand work, inverse-ROM BSRAM and additional FIFO.
        stage["logic_sites_estimate"] += 256
        stage["FF"] += 128
        stage["BSRAM"] += 2
    rows = []
    for count in range(1, len(ports) + 1):
        for ps in itertools.combinations(ports, count):
            groups = [p["exclusive_group"] for p in ps if p["exclusive_group"]]
            if len(groups) != len(set(groups)):
                continue
            names = [p["name"] for p in ps]
            i2s = sum(n.startswith("I2S") for n in names)
            signals = sum(p["pin_lower_bound"] for p in ps) - 2 * max(0, i2s - 1)
            if signals + 3 > inputs["module_gpio_capacity"] or signals + 6 > inputs["header_capacity"]:
                continue
            blocks = len({n.split("_")[0] for n in names})
            resources = dict(stage)
            resources["logic_sites_estimate"] += blocks * 128 + 192 + 96 + 1388
            resources["FF"] += blocks * 128 + 192 + 64 + 908
            resources["BSRAM"] += 4 * count + 1
            if any(resources[k] > inputs["capacity"][k] for k in resources):
                continue
            sram = 196608 + 98304 + 65536 + 32768 + 8184 * count + (100352 if st == "T" else 0)
            if sram > 524288:
                continue
            solver = pywraplp.Solver.CreateSolver("GLOP")
            u = solver.NumVar(0, 1, "utilization")
            allocations = []
            for i, f in enumerate(flows):
                vv = []
                for j, p in enumerate(ps):
                    if p["kind"] not in ("half", f["direction"]):
                        continue
                    x = solver.NumVar(0, solver.infinity(), f"flow{i}_{j}")
                    vv.append(x)
                    allocations.append((i, j, x))
                solver.Add(sum(vv) == f["MBps"])
            for j, p in enumerate(ps):
                used = sum(x for i, jj, x in allocations if jj == j)
                solver.Add(used <= u * p["effective_MBps"])
                solver.Add(cpu + 2 * used / PAYLOAD <= u)
                # An included link carries actual traffic; redundant supersets
                # are retained but not falsely called unique architectures.
                solver.Add(used >= 1e-6)
            solver.Add(cpu + 2 / mode["period_us"] <= u)
            solver.Minimize(u)
            if solver.Solve() != solver.OPTIMAL:
                continue
            aa = [{"flow": i, "port": ps[j]["name"], "MBps": x.solution_value()}
                  for i, j, x in allocations if x.solution_value() > 1e-8]
            links = []
            for p in ps:
                load = sum(a["MBps"] for a in aa if a["port"] == p["name"])
                period = PAYLOAD / load
                links.append(dict(p, used_MBps=load, spare_MBps=p["effective_MBps"] - load,
                                  arrival_us=period, additional_gap_limit_us=period - p["service_us"]))
            rows.append({"ports": names, "allocation": aa, "links": links,
                         "resources": resources, "SRAM_bytes": sram,
                         "CPU_Mcycles_s": total_cpu, "CPU_average_utilization": cpu,
                         "joint_budget_utilization": u.solution_value(),
                         "module_signals_including_controls": signals + 3,
                         "FPGA_header_signals_including_TS": signals + 6,
                         "receiver_adopted": False})
    for r in rows:
        names = set(r["ports"])
        r["inclusion_minimal"] = not any(set(q["ports"]) < names for q in rows)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = json.loads((ROOT / "reports/s3-receiver-inputs.json").read_text())
    fec = json.loads(args.fec.read_text())
    result = {"scope": "Two fixed ownerships; all subsets of the explicitly listed ports. GPIO count is a necessary condition, not an electrical pin/timing proof. No receiver is certified.",
              "FEC_kind": fec["kind"], "FEC_tool": fec["RS"]["creator"],
              "planned_S_RS": {"implemented": False, "cycles_per_block_target": 2758,
                               "minimum_clock_MHz": 2758 * 6.52125 / 188,
                               "additional_logic": 256, "additional_FF": 128, "additional_BSRAM": 2},
              "clock_plan": {"DSP_memory_MHz": 99, "TS_MHz": 66,
                             "PLL_reserved": 2, "PLL_and_full_STA_verified": False},
              "modes": {st: enumerate_mode(dict(m, standard=st), inputs, fec)
                        for st, m in inputs["modes"].items()},
              "additional_gates": ["S RS clock/cycle closure", "two-core FFT plus return transfer before buffer reuse",
                                   "RF bank deadlines and continuous acquisition", "actual linker map and DMA/SRAM arbitration",
                                   "physical pin mapping/IO constraints", "full receiver synthesis and decoder correctness"],
              "receiver_adopted": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print({st: {"sets": len(v), "minimal_sets": sum(r["inclusion_minimal"] for r in v)}
           for st, v in result["modes"].items()})


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Enumerate all 2**16 zero/nonzero BM discrepancy control trajectories.

This is an arithmetic control-flow upper bound for s3_rs_schedule.source(True),
not formal RTL equivalence or a proof of RS correction. All 204 input bytes
arrive in consecutive cycles; output has no backpressure. Regardless of how
many roots are mathematically possible, conservatively allow 8 Forney entries.
"""
import argparse
import json
from pathlib import Path


def derive(isdb=False):
    worst = None
    early_fail_count = 0
    for mask in range(1 << 16):
        degree = 0
        bm_cycles = 1  # INIT
        early_fail = False
        for n in range(16):
            # START, DISC products plus exit test, CHECK.
            bm_cycles += 3 + min(degree, n)
            if (mask >> n) & 1:
                # Inverse-ROM handoff, COEF, nine UPDATEs, POST.
                bm_cycles += 12
                if 2 * degree <= n:
                    degree = n + 1 - degree
                    if degree > 8:
                        early_fail = True
                        break
        phases = {"input": 204, "BM": bm_cycles, "Omega": 0,
                  "Chien": 0, "Forney": 0, "output_reset": 190}
        if early_fail:
            early_fail_count += 1
        else:
            phases.update(Omega=1 + sum(min(degree, j) + 3 for j in range(16)),
                          Chien=1 + 204 * max(degree, 1),
                          Forney=1 + 8 * (15 + 1 + 3 + 1 + int(isdb) + 3))
        clocks = sum(phases.values())
        if worst is None or clocks > worst["cycles"]:
            worst = {"cycles": clocks, "BM_nonzero_mask": f"0x{mask:04x}",
                     "degree": degree, "early_fail": early_fail, "phases": phases}
    return {"scope": __doc__, "ISDB_Forney_denominator_cycle": isdb, "BM_trajectories": 65536,
            "early_fail_trajectories": early_fail_count, "worst_control_path": worst,
            "S_codewords_per_second": 6_521_250 / 188,
            "S_minimum_clock_MHz": worst["cycles"] * 6.52125 / 188,
            "at_99MHz_service_us": worst["cycles"] / 99,
            "S_arrival_us": 188 / 6.52125,
            "at_99MHz_slack_us": 188 / 6.52125 - worst["cycles"] / 99}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--isdb", action="store_true")
    args = parser.parse_args()
    result = derive(args.isdb)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))

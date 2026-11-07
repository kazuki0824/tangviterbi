"""Conditional bound for two alternating eSpDR lanes, NOT measured S3 WCET.

The 3000-cycle budget includes all management, framing and fragment gaps.
Earliest delivery assumes zero such cost; latest delivery charges it all.
Only chronological out-of-order storage is bounded. In-order smoothing,
clock crossing, checksum-before-release and downstream stalls cost extra.
"""
import argparse
from fractions import Fraction
import json
import math
from pathlib import Path

MIN_N, MAX_N, CPU_MHZ, GROUP_CYCLES = 15360, 16288, 240, 91


def groups(n, alignment):
    return (n + alignment + 15) // 16


def bound(rate=40, extra_start_jitter_cycles=0, downstream_pause_cycles=0):
    if rate <= 0 or min(extra_start_jitter_cycles, downstream_pause_cycles) < 0:
        raise ValueError("positive rate and nonnegative latency required")
    # Exhaustive legal length/alignment sweep. Partial groups are retained
    # on the wire; their zero padding is never counted as missing IQ samples.
    cases = [(3000+groups(n,a)*GROUP_CYCLES+extra_start_jitter_cycles,n,a)
             for n in range(MIN_N, MAX_N+1) for a in range(16)]
    service,n,alignment = max(cases)
    min_spacing = Fraction(MIN_N*CPU_MHZ, rate)
    worker_ok = service < 2*min_spacing
    overlap = max(Fraction(0),service-min_spacing+downstream_pause_cycles)
    # Permit an instantaneous first group, then one group each 91 cycles.
    ahead_groups = math.floor(overlap/GROUP_CYCLES)+1 if overlap>0 else 0
    packed = ahead_groups*40
    expanded = ahead_groups*16*4
    one_successor = service+downstream_pause_cycles < 2*min_spacing
    admitted = worker_ok and one_successor
    return dict(rate_Msamples_s=rate, count_alignment_cases=len(cases),
        management_framing_budget_cycles=3000, budget_measured=False,
        extra_start_jitter_cycles=extra_start_jitter_cycles,
        downstream_pause_cycles=downstream_pause_cycles,
        max_service_cycles=service,max_service_us=service/CPU_MHZ,
        max_service_count=n,max_service_alignment=alignment,
        min_adjacent_release_us=float(min_spacing/CPU_MHZ),
        min_same_core_release_us=float(2*min_spacing/CPU_MHZ),
        worker_service_bound_pass=worker_ok,
        at_most_one_later_unit_bound_pass=one_successor,
        overtaking_window_us=float(overlap/CPU_MHZ),
        ahead_packed_bytes_bound=packed if admitted else None,
        ahead_expanded_iq32_bytes_bound=expanded if admitted else None,
        extra_packed_bsram_2KiB=math.ceil(packed/2048) if admitted else None,
        extra_expanded_bsram_2KiB=math.ceil(expanded/2048) if admitted else None,
        excludes=["in-order burst smoothing", "CDC FIFO", "checksum-before-release",
                  "unbounded RF/IRQ delay", "front-end processing resource cost"],
        tang_link_verified=False, receiver_adopted=False)


def report():
    return dict(scope=__doc__, source="h0m3us3r/eSpDR@f279bf823eee41796dfd1ac21f13e1ed9b418c82",
                cases=[bound(r,j,p) for r in (16,40,80)
                       for j,p in ((0,0),(2400,0),(0,2400),(2400,2400))])


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report(),indent=2)+"\n")

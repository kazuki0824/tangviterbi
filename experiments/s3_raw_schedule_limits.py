"""Necessary timing limits for raw equal-share packing; NOT a WCET proof.

The phase bound is conditional on ordinary INDEX-observation gap <= D, no
unmodelled RF counter discontinuity, and first-preparation entry no later than
the same bound after a failed reclaim. It does not prove the task schedule.
"""
from fractions import Fraction as F
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def native_constants():
    text = (ROOT / 'experiments/s3_native_capture.c').read_text()
    values = {name: int(re.search(r'\b' + name + r'=(\d+)', text)[1])
              for name in ('THRESHOLD', 'LATE', 'START', 'END')}
    match = re.search(r'written\+(\d+)/s->cpp\+(\d+)\+LATE', text)
    values.update(prepare_reserve=int(match[1]), guard=int(match[2]))
    return values


def phase_limit(rate, gap_cycles=None):
    if rate not in (16, 40):
        raise ValueError('raw T/S rate')
    c = native_constants()
    cpp = 240 // rate
    gap = c['LATE'] * cpp if gap_cycles is None else gap_cycles
    if not isinstance(gap, int) or not 0 <= gap <= c['LATE'] * cpp:
        raise ValueError('ordinary gap exceeds native lateness allowance')
    gate = c['THRESHOLD'] - c['prepare_reserve'] // cpp - c['guard'] - c['LATE']
    ceiling = c['THRESHOLD'] + c['LATE']
    advance = (gap + cpp - 1) // cpp
    # Last unavailable observation may have written=gate-1. One gap to the
    # preparation observation, then preparation plus one gap to next INDEX.
    extra = (ceiling - (gate - 1) - advance) * cpp - gap
    return dict(rate_Msample_s=rate, cpp=cpp, ordinary_gap_cycles=gap,
                unavailable_stop_written=gate, switch_limit_written=ceiling,
                latest_prepare_observation_written=gate - 1 + advance,
                max_extra_preparation_cycles=extra,
                max_extra_preparation_us=float(F(extra, 240)))


def report():
    c = native_constants()
    rows = []
    for standard, rate in (('T', 16), ('S', 40)):
        period = F(c['THRESHOLD'], rate)
        lease = F(2*c['THRESHOLD']-c['guard']-c['LATE'], rate)-F(c['prepare_reserve'], 240)
        row = phase_limit(rate)
        # Historical instruction-count sensitivity ONLY. Callee stalls, IRQs,
        # current wrapper/control costs and non-nominal bank sizes are omitted.
        fill = F(21574, 240)
        api = F(c['THRESHOLD']*5, 2*32768)*20
        row.update(standard=standard, nominal_bank_period_us=float(period),
                   earliest_native_lease_us=float(lease),
                   payload_MB_s=rate*2.5,
                   preparation_reference_ideal_us=float(fill),
                   preparation_other_cost_capacity_us=float(F(row['max_extra_preparation_cycles'], 240)-fill),
                   nominal_core0_reference_nonpacking_us=float(fill+api),
                   nominal_worker_limits=[])
        for pairs in (64, 128, 512, 1024):
            job = c['THRESHOLD']//4
            calls = (job+pairs-1)//pairs
            row['nominal_worker_limits'].append(dict(
                pairs_per_slice=pairs, slices_per_worker_bank=calls,
                core0_full_slice_average_ceiling_us=float((period-fill-api)/calls),
                core1_full_slice_average_ceiling_us=float(period/calls),
                scope='necessary nominal utilization ceilings; all omitted costs reduce these'))
        rows.append(row)
    return dict(scope=__doc__, native_constants=c, rows=rows,
                assumptions=['continuous RF/index model; hardware ABI not established',
                             'equal packing split; nominal THRESHOLD samples/bank for utilization only',
                             '21574 fill instructions treated as 21574 cycles ONLY for sensitivity',
                             '20 us active API per 32768 payload bytes ONLY for sensitivity',
                             'ordinary gap and phase-entry hypotheses must be established by scheduling'],
                source_sha256={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
                               for p in ('experiments/s3_native_capture.c',
                                         'experiments/s3_parallel_pack.c',
                                         'experiments/s3_cycle_clock.c')},
                actual_schedule_verified=False, WCET_proven=False, receiver_adopted=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report(), indent=2)+'\n')

"""Conditional first-INDEX budgets after settlement; not a measured schedule.

B is an upper bound from switch_earliest through completion of the first
post-settlement INDEX observation. Continuous rate/no discontinuity, correctly
unwrapped indices and that observation at/after the accepted end e are required.
Since e >= the switch INDEX w in this model, written <= ceil(B/cpp).
"""
import argparse
import json
import hashlib
import re
from pathlib import Path
from experiments.s3_raw_schedule_limits import native_constants, phase_limit


def limits(rate, blackout_cycles=None, preparation_cycles=None, ordinary_gap_cycles=None):
    p=phase_limit(rate,ordinary_gap_cycles);c=native_constants();cpp=p['cpp']
    for value in (blackout_cycles,preparation_cycles):
        if value is not None and (type(value) is not int or value<0):
            raise ValueError('nonnegative integer cycles or null required')
    gate=p['unavailable_stop_written'];threshold=c['THRESHOLD'];ceiling=threshold+c['LATE']
    written=None if blackout_cycles is None else (blackout_cycles+cpp-1)//cpp
    after=None if written is None or preparation_cycles is None else written+(preparation_cycles+p['ordinary_gap_cycles']+cpp-1)//cpp
    deadline=(2*threshold-c['guard']-c['LATE'])*cpp-c['prepare_reserve']
    busy_blackout=(gate-1)*cpp
    source=Path(__file__).resolve().parents[1]/'experiments/s3_native_capture.c'
    tail=int(re.search(r'count>THRESHOLD\+LATE\+(\d+)',source.read_text())[1])
    max_samples=threshold+c['LATE']+tail
    max_pairs=(max_samples+1)//2  # possible carry; floor by integer division
    worker_pairs=(max_pairs+1)//2
    return dict(rate_Msample_s=rate,cpp=cpp,
        max_accepted_bank_samples=max_samples,
        reference_slice_pairs=512,
        nominal_slices_per_worker=(threshold//4+511)//512,
        max_slices_per_worker=(worker_pairs+511)//512,
        residual_deadline_at_busy_blackout_budget_cycles=deadline-busy_blackout,
        residual_deadline_at_busy_blackout_budget_us=(deadline-busy_blackout)/240,
        residual_deadline_at_declared_blackout_cycles=None if blackout_cycles is None else deadline-blackout_cycles,
        busy_first_observation_max_written=gate-1,
        busy_blackout_upper_budget_cycles=(gate-1)*cpp,
        busy_blackout_upper_budget_us=(gate-1)*cpp/240,
        available_first_observation_max_written=threshold-1,
        available_blackout_upper_budget_cycles=(threshold-1)*cpp,
        available_blackout_upper_budget_us=(threshold-1)*cpp/240,
        blackout_upper_cycles=blackout_cycles,written_upper=written,
        busy_case_bound_within_budget=None if written is None else written<gate,
        available_prepare_entry_bound_within_budget=None if written is None else written<threshold,
        post_preparation_written_upper=after,
        prepared_next_observation_bound_within_budget=None if after is None else after<=ceiling,
        ordinary_gap_cycles=p['ordinary_gap_cycles'],switch_limit_written=ceiling,
        packing_deadline_from_switch_earliest_cycles=deadline,
        actual_schedule_verified=False,receiver_adopted=False)


def report():
    return dict(scope=__doc__,rows=[limits(16),limits(40)],
        source_sha256=hashlib.sha256((Path(__file__).resolve().parents[1]/'experiments/s3_native_capture.c').read_bytes()).hexdigest(),
        assumptions=['both relevant indices unwrap without rollover ambiguity',
                     'first post-settlement INDEX is at/after accepted end e',
                     'B includes SELECT/clock tails, settling wait and overshoot, boundary search, accept, intervening owner operations and next INDEX latency',
                     'preparation extra P plus ordinary gap D bounds the next observation interval',
                     'upper bound above a budget does not prove actual deadline failure'],
        caveats=['local first-entry conditions do not prove later reclaim availability',
                 'busy-case blackout budget is conservative, not an intrinsic maximum supported blackout',
                 'packing deadline starts at switch_earliest, not when accept publishes the bank',
                 'reported residual is before worker clock error E, publication tails, queue backlog and other work',
                 'RF ABI and numerical elapsed upper bounds remain unverified'],
        WCET_proven=False,receiver_adopted=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.write_text(json.dumps(report(),indent=2)+'\n')

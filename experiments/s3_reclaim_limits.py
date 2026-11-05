"""Conditional reclaim budget from continuous, unwrapped RF sample positions.

Let t0 be the INDEX observation at A->B, and s0=switch_earliest<=t0.
End(A)>=INDEX(t0), the following B contains >=THRESHOLD samples, and a
busy fault for reuse of A while C is active requires written(C)>=gate.
Thus that fault observes >=THRESHOLD+gate new samples since INDEX(t0).
At cpp integer cycles/sample with arbitrary phase, that observation cannot
occur before (THRESHOLD+gate-1)*cpp+1 cycles after t0. Releasing before this
strict budget relative to s0 is sufficient for this busy-gate condition only.
"""
import argparse
import hashlib
import json
from pathlib import Path
from experiments.s3_raw_schedule_limits import native_constants,phase_limit
from experiments.s3_settling_limits import limits
ROOT=Path(__file__).resolve().parents[1]


def reclaim_limits(rate):
    c=native_constants();p=phase_limit(rate);cpp=p['cpp'];gate=p['unavailable_stop_written']
    advance=c['THRESHOLD']+gate
    strict=(advance-1)*cpp+1
    packing=limits(rate)['packing_deadline_from_switch_earliest_cycles']
    return dict(rate_Msample_s=rate,cpp=cpp,busy_gate_samples=gate,
                minimum_sample_advance=advance,
                conservative_reclaim_strict_budget_cycles=strict,
                latest_certified_release_offset_cycles=strict-1,
                latest_certified_release_offset_us=(strict-1)/240,
                packing_strict_deadline_cycles=packing,
                packing_minus_reclaim_strict_cycles=packing-strict,
                collect_delay_included_in_reclaim=True,
                hardware_RF_model_verified=False,receiver_adopted=False)


def report():
    return dict(scope=__doc__,rows=[reclaim_limits(16),reclaim_limits(40)],
        assumptions=['continuous integer-cycle sample progression at declared rate',
                     'unwrapped accepted end(A) is at/after switch INDEX(A)',
                     'next accepted bank B contains at least THRESHOLD samples',
                     'only the single-owner native adapter publishes/reclaims banks',
                     'ordinary INDEX-gap, settling and preparation conditions are separately satisfied'],
        limitations=['bound guarantees release before the earliest busy-gate observation under this model only',
                     'actual gate observation can be later; exceeding this bound is not universal infeasibility',
                     'does not remove worker admission, clock-error, output-arena or SPI obligations'],
        source_sha256=hashlib.sha256((ROOT/'experiments/s3_native_capture.c').read_bytes()).hexdigest(),
        receiver_adopted=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report(),indent=2)+'\n')

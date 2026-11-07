"""Per-observation gap budgets for the current raw owner task.

These seven edges apply only when both adjacent calls take the ordinary
INDEX-reading branch. Settling calls do not read INDEX and must be composed
separately. Inputs include preemption and memory waits.
Unknown costs remain null. Passing these local constraints alone is NOT a
continuous-stream response-time, ring-capacity, utilization or WCET proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
from experiments.s3_raw_schedule_limits import phase_limit
ROOT=Path(__file__).resolve().parents[1]
# Each edge includes the prior native poll's post-INDEX work, the next poll's
# pre-INDEX work and inter-call control overhead. Preparation extra is separate.
OPERATIONS=('worker0_slice','clock_and_collect','port0_reap','port0_submit',
            'port1_reap','port1_submit','feed_and_loop')


def report(bounds=None):
    bounds={} if bounds is None else bounds
    valid=set(OPERATIONS)|{'poll_edges_'+str(i) for i in range(7)}
    if set(bounds)-valid:raise ValueError('unknown timing term')
    for value in bounds.values():
        if value is not None and (type(value) is not int or value<0):
            raise ValueError('integer nonnegative cycle upper bound or null required')
    rows=[]
    for standard,rate in (('T',16),('S',40)):
        p=phase_limit(rate);limit=p['ordinary_gap_cycles'];gaps=[]
        for i,op in enumerate(OPERATIONS):
            edge='poll_edges_'+str(i)
            values=[bounds.get(op),bounds.get(edge)]
            known=sum(v for v in values if v is not None)
            total=None if None in values else known
            verdict='bound_exceeds_budget' if known>limit else ('unproved' if total is None else 'within_declared_bounds')
            gaps.append(dict(after_poll_call_position=i+1,before_poll_call_position=(i+1)%7+1,terms=[op,edge],
                operation_upper_cycles=values[0],poll_edges_upper_cycles=values[1],
                sum_upper_cycles=total,limit_cycles=limit,
                remaining_for_unknown_terms_cycles=limit-known if total is None else None,
                slack_cycles=None if total is None else limit-total,verdict=verdict))
        rows.append(dict(standard=standard,rate_Msample_s=rate,
                         ordinary_INDEX_gap_us=limit/240,
                         extra_preparation_limit_cycles=p['max_extra_preparation_cycles'],
                         gaps=gaps,
                         all_local_constraints_within_declared_bounds=all(x['verdict']=='within_declared_bounds' for x in gaps)))
    return dict(scope=__doc__,rows=rows,
        source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
                       for p in ('experiments/s3_raw_tasks.c','experiments/s3_native_capture.c')},
        interpretation=['feed_and_loop includes the complete SDK reset when due, not its average over 2.5 seconds',
                        'reap/submit use the longest permitted active/empty/completion path',
                        'poll_edges include INDEX read latency, native branch work and all inter-call overhead',
                        'ordinary gaps exclude exceptional preparation work governed by the separate phase hypothesis',
                        'settling early-return and settlement/accept paths do not read INDEX; seven calls are not seven observations',
                        'slice_bound checks an inner sampled interval; it is not automatically worker0_slice',
                        'provided numeric bounds are declarations, not established hardware evidence',
                        'a bound above budget means this bound cannot certify the gap; it does not prove actual runtime exceeds it'],
        missing_global_proofs=['input bounds and IRQ/memory interference',
                              'INDEX blackout spanning settling polls and first next-bank preparation',
                              'bank arrival/service response time including variable bank sizes',
                              'both worker completion before RF reuse',
                              'four output arenas and out-of-order DMA retirement',
                              'SPI service at required sustained throughput'],
        WCET_proven=False,actual_schedule_verified=False,receiver_adopted=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bounds',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=report(json.loads(a.bounds.read_text()) if a.bounds else None)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2)+'\n')

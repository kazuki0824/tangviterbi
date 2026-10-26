"""Conditional two-port ordered retirement bound, in integer physical cycles.

At U[i-2] all chunks before i-1 have retired. By max(U[i-2], P[i]),
chunks i-1 and i are published. At most these two can prevent their own
submission: later chunks cannot be taken first. If either remains unsubmitted,
there is a free port. Within a complete fair two-port scan bound S both have
been submitted (or completed). Wire/driver completion takes <=max(W0,W1),
and successful reap takes <=R more. Thus U[i]=max(U[i-2],P[i])+S+max(W)+R.
The bound allows unequal ports and out-of-order completions but deliberately
charges the slowest port. Exceeding it is not physical infeasibility.
"""
import argparse
import json
import hashlib
from pathlib import Path
from experiments.s3_arena_limits import CHUNK, capacity


def integer(v,name):
    if type(v) is not int or v<0:raise ValueError(name)
    return v


def submission_horizon(n, periods):
    """Time by which n submission opportunities exist under continuous demand.

    Port p offers at least floor(t/Tp) opportunities, Tp=S+Wp+R.
    A busy transfer present at the interval start is charged in the first Tp.
    """
    if min(periods)==0:return 0
    low=0;high=n*min(periods)
    while low<high:
        mid=(low+high)//2
        if sum(mid//p for p in periods)>=n:high=mid
        else:low=mid+1
    return low


def prefix_response(published_upper, scan_bound=None, completion_bounds=None, reap_bound=None):
    for p in published_upper:integer(p,'publication upper bound')
    if published_upper!=sorted(published_upper):raise ValueError('publication prefix must be monotone')
    result=dict(status='unproved',receiver_adopted=False,actual_schedule_verified=False)
    missing=[k for k,v in (('scan_bound',scan_bound),('completion_bounds',completion_bounds),('reap_bound',reap_bound)) if v is None]
    if missing:return dict(result,missing=missing)
    integer(scan_bound,'scan_bound');integer(reap_bound,'reap_bound')
    if len(completion_bounds)!=2:raise ValueError('two ports required')
    for w in completion_bounds:integer(w,'completion bound')
    cost=scan_bound+max(completion_bounds)+reap_bound
    upper=[];pair_only=[];periods=[scan_bound+w+reap_bound for w in completion_bounds]
    for i,p in enumerate(published_upper):
        pair_only.append(max(p,pair_only[i-2] if i>=2 else 0)+cost)
        candidates=[max(p,upper[i-2] if i>=2 else 0)+cost]
        for j in range(-1,i):
            # By max(P[i], U[j]), earlier chunks have retired and every
            # target j+1..i is published. If targets remain unsubmitted,
            # each port provides an opportunity every Tp at worst. Once
            # all targets are submitted, charge the slowest completion/reap.
            start=max(p,upper[j] if j>=0 else 0)
            candidates.append(start+submission_horizon(i-j,periods)+max(completion_bounds)+reap_bound)
        upper.append(min(candidates))
    return dict(result,status='closed_within_declared_bounds',ordered_retired_upper_cycles=upper,
                pair_service_bound_cycles=cost,per_port_opportunity_cycles=periods,
                pair_only_upper_cycles=pair_only)


def connect(banks, **service):
    """Each bank supplies count, earliest accept, and latest collect/publication.

    Arrival/publication windows are supplied assumptions, not inferred WCET.
    A chunk's P comes from the first bank whose cumulative bytes cover it.
    Every chunk needed for capacity must retire strictly before earliest accept.
    """
    total=0;pub=[];obligations=[];last_accept=0;last_publish=0
    for b in banks:
        count=integer(b['samples'],'samples')
        if not count:raise ValueError('empty bank')
        a=integer(b['accept_earliest'],'accept earliest')
        p=integer(b['publish_latest'],'publish latest')
        if a<last_accept or p<max(a,last_publish):raise ValueError('invalid chronological bounds')
        total+=count;c=capacity(total,0)
        pub.extend([p]*(c['reserved_bytes']//CHUNK-len(pub)))
        obligations.append(dict(accept_earliest=a,samples=total,required=c['minimum_ordered_retired_chunks']))
        last_accept=a;last_publish=p
    result=prefix_response(pub,**service);result['obligations']=obligations
    if result['status']=='unproved':return result
    upper=result['ordered_retired_upper_cycles']
    for o in obligations:
        k=o['required'];u=upper[k-1] if k else None
        o.update(retirement_upper=u,margin_cycles=None if k==0 else o['accept_earliest']-u-1,
                 certified=k==0 or u<o['accept_earliest'])
    result['status']='capacity_certified_within_declared_bounds' if all(o['certified'] for o in obligations) else 'capacity_not_certified_by_bounds'
    return result


def report():
    root=Path(__file__).resolve().parents[1]
    return dict(scope=__doc__,result=prefix_response([]),
                source_sha256={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in
                    ('experiments/s3_raw_tasks.c','experiments/s3_parallel_pack.c','experiments/s3_parallel_spi.c')},
                assumptions=['two active ports, one outstanding transfer per port, FIFO s3_pp_take',
                             'scan bound covers a fair visit to both free ports and successful queueing, not one API call',
                             'completion bounds include queue/driver, header, payload, memory contention and completion notification',
                             'reap bound includes interrupts, owner scheduling and successful reap/complete',
                             'all bounds use the same physical cycle origin and include exceptional work',
                             'published prefix and earliest acceptance envelopes cover every actual execution'],
                limitations=['finite bank windows do not prove indefinite operation',
                             'RF reclaim/deadline and all other receiver conditions remain separate',
                             'both envelopes are sufficient bounds and can reject feasible schedules; no impossibility inference'],
                receiver_adopted=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--config',type=Path)
    args=parser.parse_args()
    data=report() if args.config is None else connect(**json.loads(args.config.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,indent=2)+'\n')

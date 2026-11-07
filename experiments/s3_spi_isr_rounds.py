"""Finite interleaving model of ONE raw SPI host's outer ISR loop.

Single registered device, no acquire_bus, one owner, one outstanding transfer.
A completion ISR publishes its old result before this loop: owner may enqueue
at most one replacement, then cannot enqueue again until that replacement's
later completion ISR. Producer enqueue precedes atomic REQ publication.
Atomic operations terminate; their retries and elapsed time are NOT modeled.
"""
import argparse
import json
import hashlib
from pathlib import Path


def successors(s):
    # pc, REQ, PEND, queued, producer phase, branch snapshot, receive success
    pc,r,p,q,producer,snap,found=s
    out=[]
    if producer==0:
        assert not q
        out.append(('enqueue',(pc,r,p,1,1,snap,found)))
    elif producer==1:
        out.append(('publish REQ',(pc,1,p,q,2,snap,found)))
    if pc==0: # schedule_core chooses sole device or yields if no BG
        out.append(('schedule',(1 if r or p else 6,r,p,q,producer,0,0)))
    elif pc==1: # check_dev_req snapshots status before moving REQ -> PEND
        out.append(('check request',(2 if r else 4 if p else 6,r,p,q,producer,r,0)))
    elif pc==2:
        out.append(('set PEND',(3,r,1,q,producer,snap,0)))
    elif pc==3:
        out.append(('clear snapshotted REQ',(4,0,p,q,producer,0,0)))
    elif pc==4: # queue receive linearization point
        out.append(('receive',(6 if q else 5,r,p,0,producer,0,q)))
    elif pc==5:
        out.append(('clear PEND',(6,r,0,q,producer,0,0)))
    elif pc==6:
        # wip=true exits unconditionally; otherwise snapshot BG for exit.
        out.append(('exit snapshot',(7,r,p,q,producer,int(bool(r or p)),found)))
    elif pc==7:
        out.append(('exit' if found or not snap else 'retry',
                    (8 if found or not snap else 0,r,p,q,producer,0,0)))
    return out


def explore(initial, concurrent_owner=True):
    memo={};visiting=set()
    def visit(s):
        if s[0]==8:return (0,[])
        if s in visiting:raise AssertionError('reachable cycle: no finite round proof')
        if s in memo:return memo[s]
        visiting.add(s);best=(-1,[])
        for label,nxt in successors(s):
            if not concurrent_owner and label in ('enqueue','publish REQ'):continue
            count,path=visit(nxt);count+=int(label=='retry')
            if count>best[0]:best=(count,[label]+path)
        visiting.remove(s);memo[s]=best;return best
    retries,path=visit(initial)
    return dict(max_outer_rounds=1+retries,witness=path,states=len(memo))


def report():
    rows=[]
    # Includes conservative stale REQ/PEND combinations and entry with no BG.
    # Pending producer: before enqueue, after enqueue, or no more producer work.
    for r in (0,1):
        for p in (0,1):
            for q,producer in ((0,0),(0,2),(1,1),(1,2)):
                initial=(0,r,p,q,producer,0,0)
                rows.append(dict(initial=list(initial),same_core=explore(initial,False),**explore(initial)))
    root=Path(__file__).resolve().parents[1]
    return dict(scope=__doc__,rows=rows,
                source_sha256={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ('experiments/s3_parallel_spi.c','experiments/s3_raw_tasks.c','reports/s3-spi-wait-audit/sources/spi_bus_lock.c','reports/s3-spi-wait-audit/sources/spi_master.c')},max_outer_rounds=max(x['max_outer_rounds'] for x in rows),
                state_count=sum(x['states'] for x in rows),
                atomic_retry_bound=None,elapsed_upper_cycles=None,
                actual_schedule_verified=False,receiver_adopted=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report(),indent=2)+'\n')

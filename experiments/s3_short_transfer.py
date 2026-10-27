"""Finite deterministic scheduling scenarios, not hardware bounds or WCET."""
import heapq,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def simulate(chunk,publication_us,scan_us,counts,budget=131072,*,scan_phase_cycles=0):
    # One physical cycle = 1/240 us. Accept at switch+16 sample periods.
    # Both ports visited on each poll, fast first, mirroring owner order.
    period=round(scan_us*240);delay=round(publication_us*240)
    assert period>0 and delay>=96 and chunk in (16384,32768)
    if type(scan_phase_cycles) is not int or not 0<=scan_phase_cycles<period:raise ValueError("scan phase outside one period")
    events=[];switch=0;total=0
    for k,n in enumerate(counts):
        total+=n;reserved=5*(total//2)
        heapq.heappush(events,(switch+96,0,reserved))
        heapq.heappush(events,(switch+delay,1,reserved))
        switch+=n*6
    published=0;submitted=0;retired=0;active=[None,None];done=set();peak=0;first_failure=None;poll=scan_phase_cycles;trace=[]
    while events or active[0] or active[1] or submitted<published//chunk:
        at=events[0][0] if events else None
        if at is not None and at<=poll:
            t,kind,amount=heapq.heappop(events)
            if kind==0:
                occupancy=amount-retired*chunk;peak=max(peak,occupancy)
                if occupancy>budget and first_failure is None:first_failure=dict(at_cycles=t,occupied_bytes=occupancy,required_bytes_over_budget=occupancy-budget)
            else:published=amount
            continue
        for port in (0,1):
            if active[port] and active[port][1]<=poll:
                done.add(active[port][0]);active[port]=None
                while retired in done:done.remove(retired);retired+=1
            if active[port] is None and submitted<published//chunk:
                duration=(chunk*8+80)*3//(8 if port==0 else 4)
                active[port]=(submitted,poll+duration);trace.append([submitted,port,poll,poll+duration]);submitted+=1
        poll+=period
    return dict(chunk_bytes=chunk,publication_us=publication_us,scan_us=scan_us,scan_phase_cycles=scan_phase_cycles,banks=len(counts),
                peak_reserved_unretired_bytes=peak,free_bytes_at_peak=budget-peak,
                first_capacity_failure=first_failure,transfers=submitted,retired=retired,
                schedule=trace,receiver_adopted=False)

def main():
    out=ROOT/'reports/s3-short-transfer';out.mkdir(exist_ok=True)
    rows=[]
    for chunk in (32768,16384):
        for h in (280,320,400):
            for scan in (20,40,80):
                for name,pattern in [('nominal',[12288]),('maximum',[14352]),('alternating',[12289,14352])]:
                    r=simulate(chunk,h,scan,(pattern*128)[:128]);r['pattern']=name
                    if not (h==320 and scan==40):r.pop('schedule')
                    rows.append(r)
    from experiments.s3_worker_response import bank_response
    limits=[]
    for publication in (280,320,400):
        for older in (0,1):
            for c0_us in (20,25,30):
                def passes(c1):
                    configs=[dict(release_delay=96,clock_error=0,ordinary_iteration=c,
                        sampled_slice=c,slice_bound=c,older_banks=older,slice_pairs=512,events=[])
                        for c in (c0_us*240,c1)]
                    return bank_response(40,configs,publication*240+1,core0_sixteenths=5)['status']=='closed_within_declared_bounds'
                lo,hi=0,publication*240
                while lo<hi:
                    mid=(lo+hi+1)//2
                    if passes(mid):lo=mid
                    else:hi=mid-1
                limits.append(dict(publication_us=publication,older_banks=older,core0_iteration_us=c0_us,
                    maximum_core1_iteration_cycles=lo,maximum_core1_iteration_us=lo/240))
    def bandwidth(gap):
        return sum(16384/((16384*8+80)/(80*lanes)+gap) for lanes in (8,4))
    low,high=0.,100.
    for _ in range(80):
        middle=(low+high)/2
        if bandwidth(middle)>100:low=middle
        else:high=middle
    result=dict(scope=__doc__,rows=rows,conditional_iteration_limits=limits,
        link_sensitivity=[dict(equal_gap_us=g,capacity_MBps=bandwidth(g),spare_MBps=bandwidth(g)-100) for g in (0,20,40,80)],
        payload_only_equal_gap_threshold_us=low,
        caveats=['Artificial accept/publication times, deterministic wire duration and periodic scans.',
                 'Finite 128-bank traces, not all RF arrival sequences or indefinite operation.',
                 'Scan period is elapsed time; CPU active/API time is separately budgeted.',
                 'Simulation continues after capacity failure to diagnose required space; actual C would return BUSY.',
                 'No FPGA receiver, PHY ABI, signal quality, DMA contention or physical timing verification.'])
    result['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'experiments/s3_short_transfer.py',ROOT/'experiments/s3_worker_response.py',ROOT/'experiments/s3_parallel_pack.c',ROOT/'experiments/s3_raw_tasks.c']}
    (out/'schedule.json').write_text(json.dumps(result,indent=2)+'\n')
    a=json.loads((ROOT/'reports/s3-asymmetric-pack/estimate.json').read_text())['rows'][-1]
    extra=100*20*(1/16384-1/32768)*100
    cpu=dict(scope='5/16 packing, prior planning model; new API frequency only, no measured timing',API_active_us_per_chunk=20,core_percent=[[v+extra for v in a['planning_core_percent'][0]],a['planning_core_percent'][1]],additional_core0_percentage_points=extra,arena_bytes=131072,lease_count=8,metadata_array_growth_bytes=48,whole_SDK_RAM_verified=False,receiver_adopted=False)
    (out/'cpu.json').write_text(json.dumps(cpu,indent=2)+'\n')
    for r in rows:
        if r['publication_us']==320 and r['scan_us']==40:print({k:r[k] for k in ('chunk_bytes','pattern','peak_reserved_unretired_bytes','free_bytes_at_peak')})
if __name__=='__main__':main()

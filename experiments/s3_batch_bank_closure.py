"""Necessary conditions for R partition batching; no firmware/WCET claims.

Retain historical RF aggregate costs, explicitly separate single-owner failure
from a hypothetical divisible workload. Event simulation is an optimistic
completion-level model: no memory stalls, arbitrary DMA-capable contiguous
buffer placement, and zero-cost inter-core publication. All checks accumulate.
"""
import hashlib
import heapq
import json
from fractions import Fraction as F
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/s3-batch-bank-closure'


def simulate(batch=32768, ring=131072, banks=4096, extra_delay=0., api_us=20., phase=0.):
    rate=40.; period=12288/rate
    # Inherited aggregate per-bank budget, perfectly split across two cores.
    latency=448.4375*period/480+extra_delay
    lease=2*period-20000/240-(1024+2000)/rate
    events=[]
    for i in range(banks):
        heapq.heappush(events,(phase+(i+1)*period+latency,1,i))
    busy=[False,False]; sent=0; produced=0; retired=0; done={}; pending={}
    peak=0; reorder=0; faults=[]; completions=0
    first_lease_fault=None
    if latency>=lease:
        first_lease_fault=dict(bank=0,latency_us=latency,lease_us=lease)
    while events:
        now,kind,index=heapq.heappop(events)
        if kind==0:
            busy[index]=False
            offset=pending.pop(index)
            done[offset]=batch; completions+=1
            while retired in done:
                retired+=done.pop(retired)
            reorder=max(reorder,sum(done.values()))
        else:
            produced+=30720
        peak=max(peak,produced-retired)
        if produced-retired>ring:
            faults.append(dict(kind='ring_capacity',time_us=now,bytes=produced-retired));break
        for port,speed in enumerate((80.,40.)):
            if not busy[port] and produced-sent>=batch:
                pending[port]=sent;sent+=batch;busy[port]=True
                heapq.heappush(events,(now+batch/speed+1+api_us,0,port))
    if first_lease_fault:faults.append(dict(kind='bank_lease',**first_lease_fault))
    # CPU gating is independent of the optimistic completion/queue trace.
    cpu_api=100.01*240*api_us/batch
    cpu_interval=[max(0.,448.4375-240),min(448.4375,240-cpu_api)]
    # Full batches drain; a final sub-batch tail remains by construction.
    tail=produced-sent
    return dict(batch=batch,ring=ring,banks=banks,extra_delay_us=extra_delay,api_us=api_us,phase_us=phase,
                bank_period_us=period,packing_latency_us=latency,bank_lease_us=lease,
                lease_margin_us=lease-latency,peak_ring_bytes=peak,
                peak_completed_out_of_order_bytes=reorder,completed_batches=completions,
                produced_bytes=produced,retired_bytes=retired,tail_bytes=tail,
                faults=faults,optimistic_trace_pass=not faults,
                aggregate_CPU_percent=(448.4375+cpu_api)/480*100,
                core0_RF_interval_Mcycles_s=cpu_interval,
                divisible_CPU_necessary_pass=cpu_interval[0]<=cpu_interval[1],
                combined_necessary_pass=not faults and cpu_interval[0]<=cpu_interval[1],
                full_receiver_pass=False)


def run():
    OUT.mkdir(exist_ok=True)
    checks=[]
    def check(name,ok):checks.append(dict(name=name,ok=bool(ok)))
    cases=[]
    for standard,rf,raw in [('T',F('185.375'),F('40.01')),('S',F('448.4375'),F('100.01'))]:
        for b in (16384,32768):
            api=raw*240*20/b
            lo=max(F(0),rf-240);hi=min(rf,240-api)
            cases.append(dict(standard=standard,batch=b,RF_high_Mcycles_s=float(rf),API_Mcycles_s=float(api),
                              current_single_owner_percent=float((rf+api)/240*100),
                              ideal_equal_RF_split_core_percent=[float((rf/2+api)/240*100),float(rf/2/240*100)],
                              feasible_core0_RF_Mcycles_interval=[float(lo),float(hi)],
                              feasible_split_exists=lo<=hi,
                              workload_actually_divisible=False))
            if standard=='S':
                caps=[F(b)/(F(b,speed)+21) for speed in (80,40)]
                cases[-1]['split_RF_and_port_owner_core_percent']=[float((rf/2+raw*c/sum(caps)*240*20/b)/240*100) for c in caps]
            check('CPU_sum_'+standard+str(b),abs(sum(cases[-1]['ideal_equal_RF_split_core_percent'])/2-float((rf+api)/480*100))<1e-9)
    sdk=json.loads((ROOT/'reports/s3-runtime-control-union-evidence/results.json').read_text())
    # Check recorded bound exists; no recursive guess of an unrelated field.
    def find(obj,key):
        vals=[]
        if isinstance(obj,dict):
            if key in obj:vals.append(obj[key])
            for v in obj.values():vals+=find(v,key)
        elif isinstance(obj,list):
            for v in obj:vals+=find(v,key)
        return vals
    check('SDK_free_before_pool_bound',30004 in find(sdk,'free_before_DMA_pool_upper_bound_bytes'))
    spare=30004-4096
    memory=[]
    for b in (16384,32768):
        for reclaim in (0,32768,32768+65536+16384):
            memory.append(dict(batch=b,reclaimed_bytes=reclaim,available_upper_bound=spare+reclaim,
                               send_buffers_bytes=4*b,remaining_upper_bound=spare+reclaim-4*b,
                               current_firmware_unchanged=reclaim==0,contiguous_DMA_regions_verified=False,
                               new_link_map_verified=False,driver_and_worker_cost_included=False))
    traces=[simulate(batch=b,ring=4*b,api_us=api,extra_delay=d,phase=p)
            for b in (16384,32768) for api in (20,40,60) for d in (0,100,200) for p in (0,)]
    for i,t in enumerate(traces):
        check('trace_capacity_status_'+str(i),(not any(f['kind']=='ring_capacity' for f in t['faults']))==(t['peak_ring_bytes']<=t['ring']))
        check('trace_lease_status_'+str(i),(not any(f['kind']=='bank_lease' for f in t['faults']))==(t['packing_latency_us']<t['bank_lease_us']))
        if not t['faults']:
            check('trace_byte_conservation_'+str(i),t['produced_bytes']==t['retired_bytes']+t['tail_bytes'] and t['tail_bytes']<t['batch'])
    # Strict poll blackout bound from native capture's LATE=2000 samples.
    poll=[]
    for rate in (16,40):
        for pack in (4,6,8):
            for chunk in (256,512,1024,13108):
                elapsed=chunk*pack/240
                poll.append(dict(rate_Msamples_s=rate,cycles_per_sample_assumed=pack,chunk_samples=chunk,
                                 nonpreemptive_pack_us=elapsed,late_limit_us=2000/rate,
                                 pack_only_necessary_pass=elapsed<=2000/rate,
                                 available_other_blackout_us=2000/rate-elapsed,
                                 measured_WCET=False))
    # Existing wire protocol is fixed-size, so a 32KiB setting alone cannot work.
    sources=['experiments/s3_native_capture.c','experiments/s3_capture_bridge.c',
             'experiments/s3_spi_transport.c','experiments/s3_spi_transport.h',
             'experiments/s3_transport.c','rtl/s3_spi_rx.sv','experiments/s3_ordered_constraints.py','reports/s3-runtime-control-union-evidence/results.json',
             'experiments/s3_batch_bank_closure.py']
    result=dict(scope=__doc__,cpu_cases=cases,memory_cases=memory,traces=traces,poll_blackouts=poll,
                checks=checks,all_checks_pass=all(c['ok'] for c in checks),
                source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
                receiver_adopted=False,formal_routes=0,
                remaining=['raw-only SDK link map','two-core bank/packing ownership implementation','IRQ/RTOS/PHY/core WCET',
                           'stream framing and FPGA buffering/clock domains','full FPGA resource and timing closure','RF to TS hardware'])
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(checks=len(checks),failed=[c for c in checks if not c['ok']],
                         cpu=cases,memory=memory,trace_passes=sum(t['optimistic_trace_pass'] for t in traces),traces=len(traces)),indent=2))
    return result

if __name__=='__main__':
    raise SystemExit(0 if run()['all_checks_pass'] else 1)

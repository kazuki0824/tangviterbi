"""Finite simultaneous T/S audit. Analytical budgets are not implemented WCET/STA.

Reads pinned repository evidence, recomputes every ownership pair and every
compatible transport subset. No transport-motivated precision/sample reduction.
"""
import argparse
import csv
import gzip
import hashlib
import io
import itertools
import json
import math
from pathlib import Path

from s3_peripheral_resources import constraints, pin_count
from s3_sct_schedule import service
from dual_s3_deadlines import RS_CYCLES, fft_schedule

ROOT = Path(__file__).resolve().parents[1]
BASE = '4f92e8ee52256375e1ce10890e77986509444332'
CAP = dict(logic_sites_estimate=20736, FF=15552, BSRAM=46, DSP18=48)
T_RS = 4992 * 6 * (7 / 8) / (1039.5e-6) / (204 * 8)
S_RS = 28.86e6 / (203 * 4)
TMCC_RS = 28.86e6 / (39936 * 8)
CONTROL = .01  # MB/s in EACH direction on each link set, design reservation


def read_gz(name):
    return json.loads(gzip.decompress((ROOT / name).read_bytes()))


def fft_budget(n=8192, clock=162):
    # 64/128-point two-factor FFT; two cycles/butterfly, one complex
    # twiddle multiply/point at four cycles. Four external complex transfers
    # for the two passes plus capture/store and final/output: six total.
    period = n / (512e6 / 63) * (33 / 32) * 1e6
    cycles = n * int(math.log2(n)) + 4 * n
    return dict(n=n, period_us=period, cycles=cycles,
                compute_us=cycles / clock,
                compute_utilization=cycles / clock / period,
                SDRAM_MBps=6 * n * 4 / period)


def profiles(legacy):
    out = []
    for p in legacy['profiles']:
        p = dict(p)
        # Recalculate; do not copy the old numeric effective-capacity column.
        c = p['capacity_Bps'] / 1e6
        if 'Octal' in p['name']:
            effective = 3 * 4096 / service(3)
            batch = 3
        elif p['name'].startswith('SPI'):
            effective = 4096 / service(1, lanes=round(c / 10), segment_us=0)
            batch = 1
        elif p['name'].startswith(('SDIO', 'eMMC')):
            effective = 4096 / ((4096 + 16) / c + (96 + 18 * 9) / 40 + 20)
            batch = 1
        else:
            effective = 4096 / ((4096 + 16) / c + (8 if p['name'].startswith(('LCD', 'CAM')) else 0))
            batch = 1
        p.update(capacity_MBps=effective, batch_pages=batch)
        out.append(p)
    return out


def port_sets(ps):
    out = []
    for n in range(1, len(ps) + 1):
        for group in itertools.combinations(ps, n):
            groups = [p['exclusive_group'] for p in group if p['exclusive_group']]
            if len(groups) != len(set(groups)):
                continue
            if pin_count(group) + 1 > 30 or not constraints(group)['gdma']['selected_driver_capacity_pass']:
                continue
            out.append(group)
    return out


def allocate(ps, up, down):
    """up=SoC->FPGA, down=FPGA->SoC; half-duplex time charged once."""
    c = {k: sum(p['capacity_MBps'] for p in ps if p['kind'] == k)
         for k in ('half', 'down', 'up')}
    # In inherited catalog 'down' denotes SoC->FPGA; avoid label inversion.
    if up > c['down'] + c['half'] or down > c['up'] + c['half'] or up + down > sum(c.values()):
        return None
    peak = max(up / (c['down'] + c['half']) if up else 0,
               down / (c['up'] + c['half']) if down else 0,
               (up + down) / sum(c.values()))
    du = min(up, c['down'] * peak)
    dd = min(down, c['up'] * peak)
    result = []
    for p in ps:
        b = p['capacity_MBps']
        if p['kind'] == 'half':
            u, d = (up - du) * b / c['half'], (down - dd) * b / c['half']
        elif p['kind'] == 'down':
            u, d = du * b / c['down'], 0
        else:
            u, d = 0, dd * b / c['up']
        result.append(dict(port=p['name'], up_MBps=u, down_MBps=d,
                           capacity_MBps=b, spare_MBps=b-u-d,
                           utilization=(u+d)/b,
                           API_Mcycles_s=(u+d)*1e6/(4096*p['batch_pages'])*4800/1e6))
    return result


def rpc_catalog(legacy, sets):
    """Every complete RPC message/port assignment, with RF sharing the ports.

    RPC pages cannot be fractionally striped. RF pages can be scheduled over
    remaining capacity. This is still an average necessary condition.
    """
    result = {}
    period_us = 204 / S_RS * 1e6
    for name, profile in legacy['RS_subpartitions'].items():
        messages = profile['records']
        routes = []
        for ps in sets:
            choices = [[i for i,p in enumerate(ps)
                        if p['kind'] in ('half', 'down' if m['direction']=='S3_to_FPGA' else 'up')]
                       for m in messages]
            if any(not c for c in choices):
                continue
            for allocation in itertools.product(*choices):
                used = [0.]*len(ps)
                for i,m in zip(allocation,messages):
                    p = ps[i]; n=m['pages']
                    if 'Octal' in p['name']:
                        duration=service(n)
                    elif p['name'].startswith('SPI'):
                        duration=n*service(1,lanes=round(p['capacity_Bps']/1e7),segment_us=0)
                    else:
                        duration=n*4096/p['capacity_MBps']
                    used[i]+=duration/period_us
                if any(u>=1 for u in used):
                    continue
                free=[]
                for p,u in zip(ps,used):
                    q=dict(p);q['capacity_MBps']*=1-u;free.append(q)
                rf=allocate(free,100+CONTROL,CONTROL)
                if rf is None:
                    continue
                routes.append(dict(ports=[p['name'] for p in ps],pins=pin_count(ps),
                    message_ports=[ps[i]['name'] for i in allocation],
                    RPC_time_fractions=used,remaining_RF_control_allocation=rf,
                    CPU_solver_WCET=None,performance_verified=False))
        result[name]=dict(messages=messages,batch_period_us=period_us,routes=routes,
                          formally_assigned=False)
    return result


def candidate_budgets():
    # Explicit allocations, NOT synthesis measurements. Conservative full-S
    # K7 path is ADDITIONAL to TC8PSK, not silently omitted.
    blocks = {
        'T_FIR_sync': [1008, 1792, 3, 9],
        'T_equalize_interleave_TS': [704, 576, 0, 5],
        'T_K7': [2952, 1502, 2, 0],
        'S_FIR_sync_frame_TS': [1128, 1472, 9, 14],
        'S_TC8PSK': [3208, 1758, 4, 2],
        'S_BPSK_QPSK_K7_extra': [2952, 1502, 2, 0],
        'RS_T': [2400, 1280, 3, 0],  # corrected decoder + one staging BSRAM allocation
        'RS_S': [2400, 1280, 3, 0],
        'FFT_tiled': [2500, 1024, 8, 8],  # revised after fixed-point tile/map P&R; allocation, not full integration
        'IO_SDRAM_TMCC_control_reserve': [3000, 2000, 13, 0],
    }
    rows = []
    for name in ('A_tiled_independent_RS', 'B_tiled_shared_RS', 'C_resident_shared_RS', 'D_SoC_FFT_shared_RS'):
        b = dict(blocks)
        clock = 162
        if name != 'A_tiled_independent_RS':
            del b['RS_T']
            b['RS_S'] = [3000, 1408, 3, 0]  # partial routed probe incl stimulus: 2786 sites/1311 FF/2 BSRAM; +staging
            clock = 162
        if name == 'C_resident_shared_RS':
            b['FFT_tiled'] = [1000, 1024, 20, 4]  # 16 data +3 exact-quarter ROM +1 reserve
        if name == 'D_SoC_FFT_shared_RS':
            b['FFT_tiled'] = [500, 512, 4, 0]  # return/CDC FIFOs; not zero cost
        res = {k: sum(v[i] for v in b.values()) for i,k in enumerate(CAP)}
        rs_rate = S_RS + TMCC_RS + (T_RS if name != 'A_tiled_independent_RS' else 0)
        f = fft_budget(clock=162)
        mem = 2 * (4992 * 6 / 1039.5) + 2 * S_RS * 204 / 1e6
        if name.startswith(('A_', 'B_')):
            mem += f['SDRAM_MBps']
        elif name.startswith('C_'):
            mem += 2 * 8192 * 4 / 1039.5
        # +10 MB/s explicitly allocated to TMCC, refresh-side buffering,
        # management and non-payload accesses (refresh bus loss is in efficiency).
        mem += 10
        rows.append(dict(id=name, blocks=dict(zip(b, [dict(zip(CAP,v)) for v in b.values()])),
                         resources=res, occupancy_percent={k:100*v/CAP[k] for k,v in res.items()},
                         clock_target_MHz=clock, RS_service_us=RS_CYCLES/clock,
                         RS_engine_utilization=RS_CYCLES*rs_rate/(clock*1e6),
                         SDRAM_required_MBps=mem, SDRAM_capacity_assumed_MBps=135*4*.65,
                         SDRAM_utilization=mem/(135*4*.65),
                         revised_after_shared_RS_synthesis=True,
                         revised_after_FFT_SDRAM_component_implementation=True,
                         resource_values_are_allocations_not_whole_synthesis=True,
                         RS_162MHz_partial_probe_pass=False,
                         full_domain_STA_qualified=False,
                         SDRAM_65percent_guaranteed=False,
                         SDRAM_efficiency_is_unverified_design_requirement=True,
                         tiled_FFT_55percent_schedule_rejected=name.startswith(('A_', 'B_')),
                         FFT_at_65percent=[{k:v for k,v in fft_schedule(n,.65).items() if k not in ('first','second')}
                                           for n in (2048,4096,8192)] if name.startswith(('A_','B_')) else None,
                         resource_budget_pass=all(res[k]<=CAP[k] for k in CAP),
                         performance_verified=False, formally_assigned_routes=0, adopted=False))
    return rows


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    legacy = read_gz('reports/s3-partition-audit/estimate.json.gz')
    original = read_gz('reports/four-soc-comparison/inputs.json.gz')
    indexed = {r['id']:r for r in legacy['assignments']}
    stage = {}
    for r in original['mode_profiles']:
        if r['id'] not in indexed:
            continue
        p = next(p for p in r['profiles'] if not p['high'] and p['FPGA_MHz']==125 and (p['RF_format']=='lossless20' or indexed[r['id']]['owners']['FIR']=='SoC'))
        stage[r['id']] = {k:sum(s[k] for s in p['FPGA_stage_estimates'].values()) for k in CAP}
        selected = indexed[r['id']]
        required = dict(p['stage_required_MHz'])
        if 'RS' in required:
            required['RS'] = 2667 * (T_RS if selected['standard']=='T' else S_RS) / 1e6
        if selected['standard']=='S' and 'trellis' in required:
            required['trellis'] = 86.58
        selected['rechecked_stage_required_MHz'] = required
        selected['T_symbol_periods_us'] = [259.875,519.75,1039.5] if selected['standard']=='T' else None
        selected['RS_peak_deadline_us'] = 1e6/(T_RS if selected['standard']=='T' else S_RS)
        selected['required_FPGA_target_MHz'] = max(required.values(),default=0)
        selected['deadline_basis'] = 'selected kernels only; missing full-S modes/driver/memory costs are NOT zero'
    ts = [r for r in indexed.values() if r['standard']=='T']
    ss = [r for r in indexed.values() if r['standard']=='S']
    records = []
    for t,s in itertools.product(ts,ss):
        res = {k:stage[t['id']][k]+stage[s['id']][k] for k in CAP}
        reasons = []
        if any(v>CAP[k] for k,v in res.items()): reasons.append('inherited_stage_only_capacity_exceeded')
        if not t['CPU_average_model_screen_pass'] or not s['CPU_average_model_screen_pass']:
            reasons.append('selected_CPU_low_model_or_arithmetic_failure')
        records.append(dict(T=t['id'],S=s['id'],stage_only_sum=res,
                            stage_only_percent={k:100*v/CAP[k] for k,v in res.items()},
                            required_selected_FPGA_MHz=max(t['required_FPGA_target_MHz'],s['required_FPGA_target_MHz']),
                            T_CPU_low_high_percent=t['CPU_low_high_percent'],
                            S_CPU_low_high_percent=s['CPU_low_high_percent'],
                            stage1_failures=reasons, full_performance_pass=None,
                            formally_assigned_routes=0, adopted=False))
    # Entire legacy finite ownership set retained, all crossings and old cost
    # models explicit; partial unknowns do not become zero-resource stages.
    data = dict(base=BASE, capacities=CAP, ownerships=list(indexed.values()),
                simultaneous_pairs=records, candidates=candidate_budgets())
    (output/'ownerships.json.gz').write_bytes(gzip.compress(json.dumps(data,sort_keys=True).encode(),mtime=0))
    ps = profiles(legacy)
    sets = port_sets(ps)
    # Do not pretend these are formal allocations past the performance gate:
    # this is a separately labelled necessary-condition catalog for every
    # ownership with an optimistic CPU screen, including all rejected pairs.
    route_cache = {}
    for r in indexed.values():
        if not r['CPU_average_model_screen_pass']: continue
        key = (r['required_down_MBps']+CONTROL,r['required_up_MBps']+CONTROL)
        if key not in route_cache:
            route_cache[key] = []
            for group in sets:
                a = allocate(group,*key)
                if a is not None:
                    route_cache[key].append(dict(ports=[p['name'] for p in group],
                        pins=pin_count(group),links=a,API_Mcycles_s=sum(p['API_Mcycles_s'] for p in a)))
    catalog = []
    for t,s in itertools.product(ts,ss):
        if not t['CPU_average_model_screen_pass'] or not s['CPU_average_model_screen_pass']:continue
        tk=(t['required_down_MBps']+CONTROL,t['required_up_MBps']+CONTROL)
        sk=(s['required_down_MBps']+CONTROL,s['required_up_MBps']+CONTROL)
        # FPGA-origin independent serial TS each uses data/clock/valid.
        ts_pins = 3*(t['owners']['TS']=='FPGA')+3*(s['owners']['TS']=='FPGA')
        count = 0
        for ti,tr in enumerate(route_cache[tk]):
            for si,sr in enumerate(route_cache[sk]):
                total_pins = tr['pins']+sr['pins']+ts_pins+2
                if total_pins>34:continue
                # Replace old 200 cycles/page; do not add API a second time.
                tcpu=t['CPU_low_high_Mcycles_s'][0]-(sum(tk)-2*CONTROL)*200/4096+tr['API_Mcycles_s']
                scpu=s['CPU_low_high_Mcycles_s'][0]-(sum(sk)-2*CONTROL)*200/4096+sr['API_Mcycles_s']
                catalog.append(dict(T=t['id'],S=s['id'],T_route=ti,S_route=si,
                                    pins=total_pins,T_CPU_low_API_percent=tcpu/4.8,
                                    S_CPU_low_API_percent=scpu/4.8,formal_assignment=False))
                count+=1
    route_data=dict(scope='necessary capacity only; NOT step-2 formal assignment',profiles=ps,
                    control_each_direction_MBps=CONTROL,parallel_gap_us=8,
                    routes={f'{k[0]:.9f},{k[1]:.9f}':v for k,v in route_cache.items()},pairs=catalog)
    rpc = rpc_catalog(legacy, sets)
    rpc_pairs=[]
    rpc_pin_cache={}
    for t in ts:
        if not t['CPU_average_model_screen_pass']:continue
        key=(t['required_down_MBps']+CONTROL,t['required_up_MBps']+CONTROL)
        for name,group in rpc.items():
            for ti,tr in enumerate(route_cache[key]):
                available=34-tr['pins']-3-3*(t['owners']['TS']=='FPGA')-2
                cache_key=(name,available)
                if cache_key not in rpc_pin_cache:
                    rpc_pin_cache[cache_key]=[(i,r) for i,r in enumerate(group['routes']) if r['pins']<=available]
                for si,sr in rpc_pin_cache[cache_key]:
                    pins=tr['pins']+sr['pins']+3+3*(t['owners']['TS']=='FPGA')+2
                    if pins<=34:
                        rpc_pairs.append(dict(T=t['id'],S_RS_partition=name,T_route=ti,S_RPC_route=si,
                                              pins=pins,formal_assignment=False))
    route_data['RS_partial_catalog']=rpc
    route_data['RS_partial_pairs']=rpc_pairs
    (output/'routes.json.gz').write_bytes(gzip.compress(json.dumps(route_data,sort_keys=True).encode(),mtime=0))
    # Human-readable exact route witnesses; keep all supersets in compressed catalog.
    target=(40+CONTROL,CONTROL);sat=(100+CONTROL,CONTROL)
    witnesses=[]
    for row in catalog:
        if (row['T'],row['S'])!=('S3-T-000','S3-S-000'):continue
        tr=route_cache[target][row['T_route']];sr=route_cache[sat][row['S_route']]
        witnesses.append({**row,'T_ports':'+'.join(tr['ports']),'S_ports':'+'.join(sr['ports']),
                          'T_spare_MBps':sum(p['spare_MBps'] for p in tr['links']),
                          'S_spare_MBps':sum(p['spare_MBps'] for p in sr['links'])})
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=list(witnesses[0]) if witnesses else ['T'],lineterminator='\n')
    writer.writeheader();writer.writerows(witnesses);(output/'raw-route-pairs.csv').write_text(stream.getvalue())
    summary=dict(base=BASE,ownership_count=len(indexed),pair_count=len(records),
                 optimistic_CPU_pairs=sum(not r['stage1_failures'] for r in records),
                 peripheral_profiles=len(ps),individual_pin_DMA_sets=len(sets),
                 simultaneous_capacity_pairs=len(catalog),raw_route_pairs=len(witnesses),
                 RS_partial_capacity_pairs=len(rpc_pairs),RS_partial_route_counts={k:len(v['routes']) for k,v in rpc.items()},
                 step1_complete=False,formal_step2_assignments=0,step3_adopted_receivers=0,
                 rates=dict(T_RS_CW_s=T_RS,S_RS_peak_CW_s=S_RS,S_RS_deadline_us=1e6/S_RS,
                            S_TMCC_CW_s=TMCC_RS,T_TS_Mbps=T_RS*188*8/1e6),
                 FFT=[fft_budget(n) for n in (2048,4096,8192)],candidates=candidate_budgets(),
                 input_sha256={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in
                    ('reports/s3-partition-audit/estimate.json.gz','reports/four-soc-comparison/inputs.json.gz')})
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('candidates','input_sha256','FFT')},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/20k-dual-s3')
    run(parser.parse_args().output)

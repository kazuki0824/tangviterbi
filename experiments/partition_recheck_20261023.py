"""Recheck fixed HEAD evidence and enumerate conditional transport alternatives.

No hardware performance pass is inferred from arithmetic. Checks accumulate;
writing audit.json and all candidate tables precedes a nonzero audit exit.
"""
import csv
import gzip
import hashlib
import io
import itertools
import json
import math
import sys
from collections import Counter
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ci.gowin_ff_site_audit import audit as site_audit
import control_only_estimate as old

OUT = ROOT / 'reports/partition-recheck-20261023'
BASE = 'f23ffeb1ec652f42c7b164e68f5162e781828090'
checks = []
inputs = {}


def read(path):
    raw = (ROOT / path).read_bytes()
    inputs[path] = hashlib.sha256(raw).hexdigest()
    return json.loads(gzip.decompress(raw) if path.endswith('.gz') else raw)


def check(name, ok, detail=None):
    checks.append(dict(name=name, ok=bool(ok), detail=detail))


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    rows = read('reports/partition-recheck-20261023/all-ownerships.json.gz')
    stored = read('reports/control-only-20k/all-ownerships.json.gz')
    check('all_320_ownership_rows_reproduced', rows == stored)
    catalog = read('reports/partition-recheck-20261023/bandwidth-catalog.json.gz')
    check('entire_bandwidth_catalog_reproduced', catalog == read('reports/control-only-20k/bandwidth-catalog.json.gz'))
    ts = [r for r in rows if r['standard'] == 'T']
    ss = [r for r in rows if r['standard'] == 'S']
    allowed = [r for r in rows if r['command_only_return_compatible']]
    for st, n in [('T', 8), ('S', 6)]:
        seen = {tuple(r['owners'][k] for k in old.ORDER[st]) for r in rows if r['standard'] == st}
        check(st + '_all_ownerships', seen == set(itertools.product(['SoC', 'FPGA'], repeat=n)))
        monotone = {('SoC',) * i + ('FPGA',) * (n-i) for i in range(n+1)}
        check(st + '_permitted_prefixes', {tuple(r['owners'][k] for k in old.ORDER[st]) for r in allowed if r['standard'] == st} == monotone)
    # Exact independent rate expressions; CPU remains an inherited sensitivity model.
    t_step = F(4992*6*7, 8) / F('1039.5')
    s_step = F('28.86') * 2 * F(7, 8)
    k7_min = 2*(t_step+s_step)*F(128, 127)
    rs_rate = (t_step*1000000/F(204*8) + F(28860000*2, 203*8) + F(28860000, 39936*8))
    rate_data = dict(T_step_Ms=float(t_step), S_step_Ms=float(s_step), K7_min_MHz=float(k7_min),
                     shared_RS_mean_MHz=float(rs_rate*2672/1000000),
                     T_periods_us=[float(F(n*63,512)*F(33,32)) for n in (2048,4096,8192)],
                     raw_T_MBps=16*20/8, raw_S_MBps=40*20/8)
    check('raw_rates', next(r for r in ts if r['id']=='S3-T-000')['forward_MBps']==40 and next(r for r in ss if r['id']=='S3-S-000')['forward_MBps']==100)
    check('legacy_CPU_recheck_all_rows', max(abs(x) for r in rows for x in r['CPU_model_recheck_error_Mcycles_s']) < 1e-8)
    # Explicit full graph product, including every forbidden pair; no fail-fast filtering.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['T', 'S', 'direction_permitted', 'T_CPU_low_pct', 'T_CPU_high_pct', 'S_CPU_low_pct', 'S_CPU_high_pct', 'stage_logic', 'stage_FF', 'stage_BSRAM', 'stage_DSP18', 'whole_performance', 'formal_routes', 'adopted'])
    for t, s in itertools.product(ts, ss):
        permitted = t['command_only_return_compatible'] and s['command_only_return_compatible']
        writer.writerow([t['id'], s['id'], permitted, *t['CPU_before_driver_percent'], *s['CPU_before_driver_percent'],
                         *(t['stage_resources'][k]+s['stage_resources'][k] for k in old.KEYS), 'unknown' if permitted else 'forbidden_return', 0, False])
    (OUT/'all-16384-pairs.csv.gz').write_bytes(gzip.compress(buffer.getvalue().encode(), mtime=0))
    # Every UART/I2C/half-duplex return alternative is retained in the catalogue.
    # Enumerate the Cartesian product with shared board pin budget for all 63 pairs.
    for key, routes in catalog.items():
        for route in routes:
            check('port_load_conservation:'+key+':'+str(route['id']), math.isclose(sum(p['forward_MBps'] for p in route['links']),route['required_MBps'], abs_tol=1e-9))
    pair_summary = []
    for t, s in itertools.product([r for r in ts if r['command_only_return_compatible']], [r for r in ss if r['command_only_return_compatible']]):
        tc, sc = catalog[f"{t['forward_MBps']:.9f}"], catalog[f"{s['forward_MBps']:.9f}"]
        # Count command alternatives by pin cost to avoid a huge duplicate listing.
        tc_count, sc_count = Counter(), Counter()
        for routes, counts in [(tc, tc_count), (sc, sc_count)]:
            for route in routes:
                for cmd in route['command_alternatives']:
                    counts[route['data_pins']+cmd['extra_pins']] += 1
        count = sum(a*b for p,a in tc_count.items() for q,b in sc_count.items() if p+q+6<=34)
        pair_summary.append(dict(T=t['id'], S=s['id'], T_catalog=f"{t['forward_MBps']:.9f}", S_catalog=f"{s['forward_MBps']:.9f}",
                                 auxiliary_pairs_with_command_alternatives=count, predicate='T.data_pins+T.command.extra_pins+S.data_pins+S.command.extra_pins+6 <= 34',
                                 shared_resource_and_pin_mapping_verified=False, performance_pass=None, formally_assigned=0, adopted=False))
    dump('all-63-route-products.json',pair_summary)
    # Audit most recent partial implementation using saved raw netlist/report.
    route=read('reports/controller-cursor-mask/route-result.json')
    net=read('reports/controller-cursor-mask/routed.json.gz')
    pnr=read('reports/controller-cursor-mask/pnr.json.gz')
    sites=site_audit(net['modules']['top']['cells'])
    check('routed_resource_recount',sites==route['physical_sites'])
    for name in ('routed.json','pnr.json'):
        check(name+'_raw_sha',hashlib.sha256(gzip.decompress((ROOT/'reports/controller-cursor-mask'/(name+'.gz')).read_bytes())).hexdigest()==route[name+'_sha256'])
    for path,h in read('reports/controller-cursor-mask/audit.json')['source_sha256'].items():
        check('source_sha:'+path,hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==h)
    mhz=pnr['fmax']['dut.clk']['achieved']
    delay=sum(route['path_delay_ns_by_type'].values())
    check('frequency_vs_path_delay',math.isclose(1000/delay,mhz,rel_tol=1e-6))
    finite=read('reports/controller-cursor-mask/finite.json')
    partial=dict(resources=sites, logic_pct=sites['packed_logic_with_ram_blockers']/20736*100,
                 BSRAM=pnr['utilization']['BSRAM'], DSP18=pnr['utilization']['MULT18X18'], probe_ALU54D=pnr['utilization']['ALU54D'], fmax_MHz=mhz, required_K7_MHz=float(k7_min), required_design_MHz=1080/7,
                 K7_utilization_pct=float(k7_min)/mhz*100, design_period_shortfall_ns=delay-1000/(1080/7),
                 finite_margin_cycles=2566080-finite['clients'][2]['finish'], whole_resources=None,
                 full_receiver_pass=None, measured_partial_speed_pass=mhz>=float(k7_min))
    # Reconstruct prior resource allocations, explicitly distinct from current partial.
    import recovery_resource_audit
    recovery=recovery_resource_audit.run()
    check('recovery_all_blocks_sum',recovery==read('reports/recovery-resource-audit.json'))
    import shared_k7_budget
    k7=shared_k7_budget.run()
    dump('recomputed-k7-resource-variants.json',k7)
    # New lossless batching hypotheses. Public DMA transactions, NOT existing SCT firmware.
    # 80-bit header is serialized at single-bit 80MHz (conservative 1us).
    # 20us/API is sensitivity, not a measured upper bound. Each host has 2 buffers.
    batches=[]
    for size in (4096,12288,16384,32768):
        cap8=size/(size/80+1+20)
        cap4=size/(size/40+1+20)
        need=100.01
        cpu=448.4375+need*240*20/size
        batches.append(dict(batch_bytes=size, S_Octal_capacity_MBps=cap8,S_Quad_capacity_MBps=cap4,
                            S_spare_MBps=cap8+cap4-need, S_CPU_high_pct=cpu/4.8,
                            S_CPU_unmodelled_budget_Mcycles_s=480-cpu, S_double_buffers_bytes=4*size,
                            T_double_buffers_bytes=2*size, T_Octal_spare_MBps=cap8-40.01,
                            T_CPU_high_pct=(185.375+40.01*240*20/size)/4.8,
                            S_max_API_active_us_for_aggregate_CPU=(480-448.4375)*size/(need*240),
                            S_ports=[dict(name=n,load_MBps=need*c/(cap8+cap4),capacity_MBps=c,
                                          spare_MBps=c-need*c/(cap8+cap4),batch_arrival_us=size/(need*c/(cap8+cap4)),
                                          transaction_service_us=size/(80 if n=='SPI2_Octal80' else 40)+21)
                                     for n,c in [('SPI2_Octal80',cap8),('SPI3_Quad80',cap4)]],
                            pins_with_T_Octal_UARTs_TS=34, firmware_implemented=False,
                            complete_SRAM_budget=None, per_core_WCET=None, performance_pass=None, adopted=False))
    for b in batches:
        size=b['batch_bytes']
        exact_caps=[F(size)/(F(size,speed)+21) for speed in (80,40)]
        check('batch_capacity_'+str(size), math.isclose(float(sum(exact_caps)-F(10001,100)),b['S_spare_MBps'],abs_tol=1e-10))
        check('batch_CPU_'+str(size), math.isclose(float((F('448.4375')+F(10001,100)*4800/size)/F('4.8')),b['S_CPU_high_pct'],abs_tol=1e-10))
        check('batch_port_conservation_'+str(size), math.isclose(sum(p['load_MBps'] for p in b['S_ports']),100.01,abs_tol=1e-10))
        check('batch_buffer_count_'+str(size), b['S_double_buffers_bytes']==2*2*size and b['T_double_buffers_bytes']==2*size)
        for p in b['S_ports']:
            check('batch_service_consistency_'+str(size)+p['name'], (p['transaction_service_us']<=p['batch_arrival_us'])==(b['S_spare_MBps']>=0))
    dump('batching-hypotheses.json',batches)
    gpio=old.dedicated_gpio()
    for g in gpio:
        g['forward_config_MBps']=.01
        g['spare_after_forward_config_MBps']=g['spare_MBps']-.01
        g['config_framing_CPU_unverified']=True
    gpio_pairs=[]
    for t,s in itertools.product([r for r in gpio if r['rate_Msamples_s']==16],[r for r in gpio if r['rate_Msamples_s']==40]):
        pins=t['data_clock_pins']+s['data_clock_pins']+8
        gpio_pairs.append(dict(T=t,S=s,pins_with_UARTs_TS=pins,pin_count_pass=pins<=34,
                               clock_and_memory_verified=False,performance_pass=None,adopted=False))
    for pair in gpio_pairs:
        pair['command_alternatives'] = [dict(T=tc,S=sc,pins=pair['T']['data_clock_pins']+pair['S']['data_clock_pins']+tp+sp+6,T_command_spare_MBps=tm,S_command_spare_MBps=sm) for tc,tp,tm in [('UART_1M_8N1',1,.09),('I2C_400k',2,.03)] for sc,sp,sm in [('UART_1M_8N1',1,.09),('I2C_400k',2,.03)] if pair['T']['data_clock_pins']+pair['S']['data_clock_pins']+tp+sp+6<=34]
    dump('gpio-pairs.json',gpio_pairs)
    # Mixed GPIO/peripheral pairs are also enumerated. Different SoCs do not share CPU.
    mixed=[]
    for gpio_st, rate, other_rate in [('T',16,100),('S',40,40)]:
        for g in [x for x in gpio if x['rate_Msamples_s']==rate]:
            for route in catalog[f'{other_rate:.9f}']:
                for cmd in route['command_alternatives']:
                    for gcmd,gpins in [('UART_1M_8N1',1),('I2C_400k',2)]:
                        pins=g['data_clock_pins']+gpins+route['data_pins']+cmd['extra_pins']+6
                        if pins<=34:
                            mixed.append(dict(GPIO_standard=gpio_st,GPIO_lanes=g['lanes'],GPIO_command=gcmd,
                                              peripheral_standard='S' if gpio_st=='T' else 'T',route_id=route['id'],command=cmd['route'],pins=pins,
                                              GPIO_spare_MBps=g['spare_after_forward_config_MBps'],peripheral_spare_MBps=cmd['forward_spare_MBps'],
                                              physical_verified=False,formal_assignment=False))
    old.gz_json(OUT/'mixed-gpio-peripheral.json.gz',mixed)
    # Full before/after route CPU table, still auxiliary because FPGA gate failed.
    raw=[]
    for t,s in itertools.product(catalog['40.000000000'],catalog['100.000000000']):
        if t['data_pins']+s['data_pins']+8<=34:
            raw.append(dict(T=t['ports'],S=s['ports'],T_margin_MBps=t['spare_MBps'],S_margin_MBps=s['spare_MBps'],
                            T_CPU_high_pct=(185.375+t['driver_active_model_Mcycles_s'])/4.8,
                            S_CPU_high_pct=(448.4375+s['driver_active_model_Mcycles_s'])/4.8))
    check('raw_UART_pairs_18',len(raw)==18)
    dump('raw-18-routes-with-CPU.json',raw)
    old.gz_json(OUT/'all-checks.json.gz', checks)
    dump('audit.json',dict(base_HEAD=BASE,check_count=len(checks),check_details='all-checks.json.gz',failures=[c for c in checks if not c['ok']],all_checks_pass=all(c['ok'] for c in checks),
                          inputs_sha256=inputs,rates=rate_data,latest_partial=partial,
                          counts=dict(ownerships=len(rows),pairs=len(ts)*len(ss),allowed_pairs=len(pair_summary),
                                      mixed_gpio_peripheral=len(mixed)),
                          performance_passed=0,formal_routes=0,adopted=0,
                          scope='Finite stage/profile catalogue only; no proof about all algorithms or arbitrary PHYs'))
    print(json.dumps(dict(checks=len(checks),failed=[c['name'] for c in checks if not c['ok']],partial=partial,batches=batches),indent=2))
    return 0 if all(c['ok'] for c in checks) else 1

if __name__=='__main__':
    sys.exit(main())

"""Compare every permitted prefix with raw IQ under frozen CPU sensitivities.
No measured WCET, new route assignment, or universal impossibility claim.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from control_only_estimate import cpu_before_driver, ORDER

ROOT = Path(__file__).resolve().parents[1]
INPUT = 'reports/partition-recheck-20261023/all-ownerships.json.gz'
FIXTURE = 'reports/s3-partition-audit/inputs.json.gz'

def report():
    all_rows=json.loads(gzip.decompress((ROOT/INPUT).read_bytes()))
    fixture=json.loads(gzip.decompress((ROOT/FIXTURE).read_bytes()))
    source={r['id']:r for r in fixture['assignments'] if r['SoC']=='S3'}
    permitted=[r for r in all_rows if r['command_only_return_compatible']]
    raw={s:next(r for r in permitted if r['standard']==s and all(r['owners'][n]=='FPGA' for n in ORDER[s])) for s in ORDER}
    checks=[]
    def check(name,condition):checks.append(dict(name=name,passed=bool(condition)))
    check('all_permitted_boundaries',len(permitted)==16)
    check('T9_S7',sum(r['standard']=='T' for r in permitted)==9 and sum(r['standard']=='S' for r in permitted)==7)
    out=[]
    for r in permitted:
        s=r['standard'];b=raw[s];rate=r['forward_MBps'];base_rate=b['forward_MBps']
        cpu=cpu_before_driver(source[r['id']])
        for k in range(2):
            check(r['id']+'_CPU_recheck_'+str(k),math.isclose(cpu[k],r['CPU_before_driver_Mcycles_s'][k],abs_tol=1e-9))
        # Same batch and active-time scenario; 0.01 MB/s command allowance kept.
        api=(rate+0.01)*240*20/32768
        base_api=(base_rate+0.01)*240*20/32768
        extra=[cpu[k]-b['CPU_before_driver_Mcycles_s'][k] for k in range(2)]
        savings=base_api-api
        total=[c+api for c in cpu]
        delta=[extra[k]-savings for k in range(2)]
        # Give candidate ALL transfer CPU for free as an optimistic comparison.
        free_delta=[cpu[k]-(b['CPU_before_driver_Mcycles_s'][k]+base_api) for k in range(2)]
        for k in range(2):
            check(r['id']+'_difference_'+str(k),math.isclose(delta[k],total[k]-b['CPU_before_driver_Mcycles_s'][k]-base_api,abs_tol=1e-8))
        out.append(dict(id=r['id'],standard=s,prefix=[n for n in ORDER[s] if r['owners'][n]=='SoC'],
            forward_MBps=rate,flows=r['flows'],CPU_before_link_Mcycles_s=cpu,
            API_Mcycles_s=api,net_prelink_increase_vs_raw_Mcycles_s=extra,
            API_saving_vs_raw_Mcycles_s=savings,
            CPU_after_link_percent=[x/4.8 for x in total],
            net_increase_vs_raw_Mcycles_s=delta,
            candidate_zero_API_increase_vs_raw_Mcycles_s=free_delta,
            beats_raw_same_sensitivity=[x<0 for x in delta],
            even_zero_API_beats_raw_same_sensitivity=[x<0 for x in free_delta],
            stage_resources=r['stage_resources'],stage_resources_are_incomplete=True,
            endpoint_note='SoC TS output; not the current FPGA independent TS endpoint' if r['owners']['TS']=='SoC' else 'FPGA TS output',
            formal_routes=[],receiver_adopted=False))
    for s in ORDER:
        processed=[r for r in out if r['standard']==s and r['prefix']]
        check(s+'_all_existing_processed_models_cost_more_even_zero_API',all(all(x>0 for x in r['candidate_zero_API_increase_vs_raw_Mcycles_s']) for r in processed))
    return dict(scope=__doc__,assumptions=['32 KiB per API, 20 us CPU active, 240 MHz x 2','Both same low or same high sensitivity compared; not WCET limits','Reuse net prelink costs: do NOT add raw packing again to processed candidates','No quality-lowering extra software decimation/requantization','API comparison is auxiliary sensitivity, not actual endpoint/route implementation','Other algorithms, intra-stage cuts and hardware preprocessing not exhaustively bounded'],checks=checks,rows=out,
        input_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in (INPUT,FIXTURE,'experiments/control_only_estimate.py')},complete_estimate=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=report();a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'results.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    lines=['| ID | SoC前処理 | 送信 MB/s | 前処理後CPU低/高 % | rawとの差 低/高 Mcycles/s | API削減 Mcycles/s |', '|---|---|---:|---:|---:|---:|']
    for x in r['rows']:
        lines.append('| '+x['id']+' | '+(', '.join(x['prefix']) or 'RFのみ')+' | '+f"{x['forward_MBps']:.6f}"+' | '+' / '.join(f'{v:.3f}' for v in x['CPU_after_link_percent'])+' | '+' / '.join(f'{v:.3f}' for v in x['net_increase_vs_raw_Mcycles_s'])+' | '+f"{x['API_saving_vs_raw_Mcycles_s']:.6f}"+' |')
    (a.output/'all-prefixes.md').write_text('\n'.join(lines)+'\n')
    failures=[c for c in r['checks'] if not c['passed']]
    print(json.dumps(dict(checks=len(r['checks']),failures=failures)))
    raise SystemExit(bool(failures))

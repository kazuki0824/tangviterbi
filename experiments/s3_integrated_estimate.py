"""Integrated conditional engineering estimate; no measured cycle interval."""
import gzip,json,hashlib
from pathlib import Path
from ci.s3_pack_path_audit import run
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/receiver-integrated-estimate'
def read(path):
    p=ROOT/path
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_text())
def main():
    cfg=read('reports/s3-spi-running-guard/cfg-S/results.json');other_cfg=read('reports/s3-spi-running-guard/cfg-T/results.json')
    assert all(c['passed'] for c in cfg['checks']+other_cfg['checks'])
    assert cfg['coefficients']==other_cfg['coefficients']
    coeff=cfg['coefficients'];cpu=[]
    fill_target=read('reports/s3-budgeted-fill/u8/target.json')
    assert all(c['passed'] for c in fill_target['checks'])
    assert fill_target['source_sha256']==hashlib.sha256((ROOT/'experiments/s3_native_capture.c').read_bytes()).hexdigest()
    fill_bound=fill_target['rows'][0]['fill_instruction_envelope_per_bank']
    for share,standard,rate,chunk in ((8,'T',16,32768),(5,'S',40,16384),(6,'S',40,16384)):
        paths=run(share,[11264,12288,12289,14288,14352]);assert all(c['passed'] for c in paths['checks'])
        paths.update(core0_sixteenths=share,bank_sizes=[11264,12288,12289,14288,14352])
        (OUT/f'paths-{standard}-{share}.json').write_text(json.dumps(paths,indent=2)+'\n')
        cases=[]
        for r in paths['rows']:
            if r['slice_pairs']!=512:continue
            work=[sum(coeff[c]*v[k] for c,k in [('block','blocks_s'),('run','runs_s'),('slow_pair','slow_pairs_s'),('slice','slices_s')])/1e6 for v in r['rates'][standard]]
            cases.append(dict(samples=r['bank_samples'],first=r['first'],packing_Minstructions_s=work,
                packing_only_average_bank_us=[v*1.1*r['bank_samples']/rate/240 for v in work]))
        # Initial short banks are transient examples, not a sustained bank rate.
        steady=[r for r in cases if r['samples']>=12288]
        pack=[[min(r['packing_Minstructions_s'][w] for r in steady),max(r['packing_Minstructions_s'][w] for r in steady)] for w in (0,1)]
        core=[[1.1*(v+21574*rate/12288)/2.4+(rate*2.5)*20/chunk*100+20/2.4 for v in pack[0]],[(1.1*v+10)/2.4 for v in pack[1]]]
        row=dict(standard=standard,share=share,chunk_bytes=chunk,cases=cases,core_percent_base=core)
        fill_saving_pct=1.1*(21574-fill_bound)*rate/12288/2.4
        scan_cost=1500/288 if standard=='S' else 0
        row['implemented_fill_envelope_instructions']=fill_bound
        row['implemented_fill_and_scan1500_core_percent']=[[v-fill_saving_pct+scan_cost for v in core[0]],core[1]]
        row['prepare_management_sensitivity']=[dict(additional_cycles_per_owner_iteration=e,assumed_owner_period_us=30,core0_percent=[v+e/72 for v in row['implemented_fill_and_scan1500_core_percent'][0]]) for e in (0,100,200,300)]
        row['prepare_management_budget_cycles_per_iteration']=(100-row['implemented_fill_and_scan1500_core_percent'][0][1])*72
        row['implemented_fill_scan_budget_cycles']=(100-core[0][1]+fill_saving_pct)*288 if standard=='S' else None
        if standard=='S':
            row['implemented_fill_scan_cost_sensitivity']=[dict(additional_cycles_per_scan=c,core0_percent=[v-fill_saving_pct+c/288 for v in core[0]]) for c in (0,500,1500,3000)]
            row['additional_scan_cost_sensitivity']=[dict(additional_cycles_per_scan=c,core0_percent=[v+c/288 for v in core[0]]) for c in (0,500,1500,3000)]
            row['additional_scan_budget_cycles']=(100-core[0][1])*288
            fill_pct=1.1*21574*rate/12288/2.4
            row['fill_reduction_25pct_and_scan_1500_cycles_core0']=[v+1500/288-fill_pct*.25 for v in core[0]]
            row['minimum_fill_reduction_fraction_at_scan1500']=max(0,(core[0][1]+1500/288-100)/fill_pct)
        cpu.append(row)
    ledger=read('reports/partition-recheck-20261023/recomputed-k7-resource-variants.json')
    owners=read('reports/partition-recheck-20261023/all-ownerships.json.gz');raw=next(r for r in owners if r['id']=='S3-T-000');fir=next(r for r in owners if r['id']=='S3-T-001')
    saved={k:raw['stage_resources'][k]-fir['stage_resources'][k] for k in raw['stage_resources']}
    caps=dict(logic_sites_estimate=20736,FF=15552,BSRAM=46,DSP18=48);fpga=[]
    for r in ledger['cases']:
        for move in (False,True):
            area={k:r['R_H_replacement'][k]-(saved[k] if move else 0) for k in caps}
            fpga.append(dict(kernel=r['trial'],T_FIR_on_SoC=move,whole_ledger=area,remaining={k:caps[k]-area[k] for k in caps},standalone_kernel_MHz=next(iter(r['fmax'].values()))['achieved'],whole_PnR_verified=False))
    pnr=read('reports/controller-cursor-mask/pnr.json.gz')
    path=max(pnr['critical_paths'],key=lambda p:sum(x['delay'] for x in p['path']))
    routing=sorted([p['delay'] for p in path['path'] if p['type']=='routing'],reverse=True)
    actual=pnr['fmax']['dut.clk']['achieved'];minimum=2*(25.212121+50.505)*128/127;target=1080/7
    q=read('reports/s3-preprocess-break-even/qacc/qacc-audit.json')['rows'][0]
    optimistic=[v+q['optimistic_kernel_Mcycles_s']+q['separate_prepare_write_only_ideal_Mcycles_s'] for v in q['inherited_non_FIR_plus_API_Mcycles_s']]
    result=dict(scope=__doc__,cpu=cpu,FPGA=fpga,T_FIR_removed=saved,
        partial_timing=dict(MHz=actual,minimum_MHz=minimum,target_MHz=target,largest_routing_ns=routing[:2],minimum_path_reduction_ns=1000/actual-1000/minimum,target_path_reduction_ns=1000/actual-1000/target),
        T_FIR_optimistic_legacy_Mcycles_s=optimistic,T_FIR_optimistic_legacy_remaining=[480-v for v in optimistic],
        caveats=['Old whole-stage allocation plus replacement kernels, not a whole-top synthesis.',
        'Packing coefficients are recounted from current S/T SDK CFGs; alpha=1.1, API=20us, U=20/10 Mcycles/s remain assumptions.',
        'Extra scan cycles 500/1500/3000 are sensitivity points, not measured percentiles.',
        'T FIR optimistic aggregate mixes retained legacy non-FIR budget with compiled kernel instruction and preparation-write floor; gather reads, unpack, contention and quality unverified.',
        'Formal performance pass, route assignment and receiver adoption remain zero.'],receiver_adopted=False)
    sdk=read('reports/s3-spi-running-guard/sdk-S/sdk-verification.json')
    assert all(c['passed'] for c in sdk['checks'])
    result['S_candidate_SDK']=dict(commit=sdk['commit'],checks=sdk['SDK_static_checks'],
        driver=sdk['driver_lower_bound'],symbols=sdk['symbols'],sizes=sdk['sizes'],
        actual_boot_verified=False)
    result['owner_schedule']=dict(fill_envelope_us_at_alpha1_1=fill_bound*1.1/240,
        maximum_prepare_words_per_owner_iteration=fill_target['prepare_quantum_words'],
        maximum_fill_call_instructions=fill_target['maximum_fill_call_instruction_envelope'],
        maximum_fill_call_us_at_alpha1_1=fill_target['maximum_fill_call_instruction_envelope']*1.1/240,
        requested_scan_period_us=30,constant_scan_schedule_verified=False,
        reason='Owner shares a 1024-word preparation budget across seven RF polls; other owner work and preparation availability/deadline remain to be bounded.')
    trial=ROOT/'reports/cursor-mask-timingweight20/result.json'
    if trial.exists():result['FPGA_timingweight20_trial']=json.loads(trial.read_text())
    trial=ROOT/'reports/cursor-mask-timingweight10-seed2/result.json'
    if trial.exists():result['FPGA_timingweight10_seed2_trial']=json.loads(trial.read_text())
    comparison=read('reports/cursor-mask-route-comparison/audit.json')
    assert comparison['all_checks_pass']
    best=max(comparison['rows'],key=lambda r:r['MHz'])
    result['partial_timing']['scope']='Archived baseline, not the current best route'
    result['current_partial_timing']=best
    result['current_partial_timing']['scope']='Same frozen partial circuit; not current transport plus whole receiver'
    quiet=read('reports/s3-owner-quiet-path/results.json')
    result['owner_quiet_partial']={k:quiet[k] for k in ('ELF_sha256','RF_poll_including_callbacks_instructions','partial_iteration_instructions','partial_iteration_cycles_at_alpha1_1','conditions','exclusions','CPU_estimate_reduced')}
    result['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['reports/s3-owner-quiet-path/results.json','experiments/s3_integrated_estimate.py','ci/s3_pack_path_audit.py','experiments/s3_native_capture.c','reports/s3-budgeted-fill/u8/target.json','reports/s3-spi-running-guard/cfg-S/results.json','reports/s3-spi-running-guard/cfg-T/results.json','reports/s3-spi-running-guard/sdk-S/sdk-verification.json','reports/partition-recheck-20261023/recomputed-k7-resource-variants.json','reports/controller-cursor-mask/pnr.json.gz','reports/cursor-mask-route-comparison/audit.json','reports/cursor-mask-timingweight20/result.json','reports/cursor-mask-timingweight10-seed2/result.json','reports/s3-preprocess-break-even/qacc/qacc-audit.json']}
    (OUT/'estimate.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(cpu=[{k:v for k,v in r.items() if k!='cases'} for r in cpu],FIR_saved=saved,timing=result['partial_timing'],FIR_optimistic=optimistic),indent=2))
if __name__=='__main__':main()

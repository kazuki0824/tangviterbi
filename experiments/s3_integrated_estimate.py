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
    iteration=read('reports/s3-owner-iteration-path/results.json')
    result['owner_iteration_examples']={k:iteration[k] for k in ('rows','conditions','exclusions','inline_wrapper_correction_instructions','CPU_estimate_reduced')}
    result['full_scan_reconciliation']=read('reports/s3-cost-reconciliation/results.json')
    joint=read('reports/s3-joint-runtime/results.json')
    result['joint_runtime_cost_scenarios']={
        'report':'../s3-joint-runtime/results.json', 'conditions':len(joint['rows']),
        'cost_ledger_and_virtual_elapsed_reconciled':all(all(r['elapsed_accounting_identity']) for r in joint['rows']),
        'actual_owner_order_used':True,
        'T_reference_4000_banks_pass':next(r['scenario_pass'] for r in joint['rows'] if r['requested_banks']==4000),
        'S_declared_scenarios_pass':all(r['scenario_pass'] for r in joint['rows'] if r['rate']==40),
        'all_SoC_costs_finalized':False, 'receiver_adopted':False}
    sdk_runtime=read('reports/s3-sdk-cost-ledger/runtime.json')
    sdk_rows=[r for p in sdk_runtime['profiles'] for r in p['rows']]
    result['sdk_cost_runtime_scenarios']=dict(report='../s3-sdk-cost-ledger/README.md',conditions=len(sdk_rows),S_pass_count=sum(r['scenario_pass'] for r in sdk_rows if r['rate']==40),T_pass_count=sum(r['scenario_pass'] for r in sdk_rows if r['rate']==16),all_SoC_costs_finalized=False,receiver_adopted=False)
    receiver=read('reports/s3-receiver-cost-ledger/runtime.json')
    rrows=[r for p in receiver['profiles'] for r in p['rows']]
    result['receiver_cost_runtime_scenarios']=dict(report='../s3-receiver-cost-ledger/README.md',conditions=len(rrows),S_long_pass_count=sum(r['scenario_pass'] for r in rrows if r['rate']==40 and r['requested_banks']==4000),T_long_pass_count=sum(r['scenario_pass'] for r in rrows if r['rate']==16 and r['requested_banks']==4000),all_SoC_costs_finalized=False,receiver_adopted=False)
    orders=read('reports/s3-owner-order-estimate/results.json')
    orows=[r for p in orders['profiles'] for r in p['rows']]
    result['owner_order_scenarios']=dict(report='../s3-owner-order-estimate/README.md',orders=24,short_conditions=sum(r['requested_banks']==100 for r in orows),S_long_conditions=sum(r['rate']==40 and r['requested_banks']==4000 for r in orows),S_long_pass_count=sum(r['rate']==40 and r['requested_banks']==4000 and r['scenario_pass'] for r in orows),all_SoC_costs_finalized=False,receiver_adopted=False)
    counter=read('reports/s3-counter-envelope/runtime.json')
    waits=read('reports/s3-wait-cost/runtime.json')
    result['counter_wait_scenarios']=dict(counter_report='../s3-counter-envelope/README.md',wait_report='../s3-wait-cost/README.md',counter_rows=sum(len(p['rows']) for p in counter['profiles']),wait_profiles=len(waits['profiles']),S_long_pass_count=sum(r['scenario_pass'] for p in counter['profiles'] for r in p['rows'] if r['rate']==40 and r['requested_banks']==4000),all_SoC_costs_finalized=False,receiver_adopted=False)
    queue=read('reports/s3-queue-study/runtime.json')
    extended=read('reports/s3-queue-study/extended.json')['rows'][0]
    inline=read('reports/s3-inline-packing/instructions.json')
    result['depth_two_queue_candidate']=dict(report='../s3-queue-study/README.md',scenarios=len(queue['rows']),long_banks=extended['banks'],long_requested_banks=extended['requested_banks'],long_pass=extended['scenario_pass'],arena_peak_bytes=extended['peak_arena_bytes'],RF_poll_gap_cycles=extended['max_rf_poll_gap'],SDK_API_link_verified=True,SDK_costs_audited=False,all_SoC_costs_finalized=False,receiver_adopted=False)
    audited=read('reports/s3-queue-study/audited-runtime.json')
    long=next(r for r in audited['rows'] if r['requested_banks']==20000)
    fees=read('reports/s3-queue-study/sdk-n16r8/costs.json')
    result['depth_two_queue_candidate']['scope']='Historical pre-SDK-cost sensitivity'
    result['depth_two_queue_audited_candidate']=dict(report='../s3-queue-study/README.md',scenarios=len(audited['rows']),long_banks=long['banks'],long_pass=long['scenario_pass'],arena_peak_bytes=long['peak_arena_bytes'],RF_poll_gap_cycles=long['max_rf_poll_gap'],fees_cycles=fees['fees_cycles'],memory=fees['memory'],SDK_declared_paths_audited=True,all_SoC_costs_finalized=False,receiver_adopted=False)
    result['inline_packing_candidate']=dict(report='../s3-inline-packing/README.md',block_instructions=[{k:r[k] for k in ('variant','optimization','total_per_eight_samples','step_text_bytes','step_stack_entry')} for r in inline['rows']],full_slice_cost_audited=False)
    result['legacy_cpu_accounting_validated']=False
    inline_costs=read('reports/s3-inline-packing/slice-costs.json')
    inline_runtime=read('reports/s3-queue-study/inline-runtime.json')
    inline_long=next(r for r in inline_runtime['rows'] if r['requested_banks']==20000)
    result['inline_packing_candidate'].update(full_slice_cost_audited=True,scope='Instruction envelope with inherited clock/wrapper costs, not hardware WCET',coefficients=inline_costs['coefficients'],fees_cycles=inline_costs['fees_cycles'],long_pass=inline_long['scenario_pass'],long_banks=inline_long['banks'],arena_peak_bytes=inline_long['peak_arena_bytes'],RF_poll_gap_cycles=inline_long['max_rf_poll_gap'],report='../s3-inline-packing/README.md')
    owner=read('reports/s3-queue-owner/runtime.json')
    owner_long=next(r for r in owner['rows'] if r['requested_banks']==20000)
    owner_cost=read('reports/s3-queue-owner/instructions.json')
    memory=read('reports/s3-queue-owner/memory.json')
    result['queue_connected_owner_candidate']=dict(report='../s3-queue-owner/README.md',scope='Actual generated normal-receive owner; finite instruction-cost model, not hardware WCET',replacement_fees_cycles=owner_cost['replacement_fees_cycles'],long_result=owner_long,memory_necessary_pass=memory['memory_necessary_pass'],driver_allocation_bound=memory['driver_lower_bound'],cost_and_memory_probe_CFGs_match=memory['control_and_packing_CFGs_match_cost_probe'],all_SoC_costs_finalized=False,receiver_adopted=False)
    result['queue_connected_owner_candidate']['event_rates_per_core_accounted_horizon']=[dict(horizon_cycles=owner_long['accounted_until_cycles'][core],events={name:dict(count=v['events'],events_per_second=v['events']*240000000/owner_long['accounted_until_cycles'][core],charged_cycles=v['cycles']) for name,v in ledger.items()}) for core,ledger in enumerate(owner_long['cost_ledger'])]
    result['queue_connected_owner_candidate']['retained_allocation_refinement']=read('reports/s3-queue-owner/allocations.json')
    result['queue_connected_owner_candidate']['lifetime_memory_refinement']=read('reports/s3-queue-owner/lifetime-memory.json')
    result['queue_connected_owner_candidate']['periodic_PHY_audit']=read('reports/s3-queue-owner/phy-periodic.json')
    result['queue_connected_owner_candidate']['periodic_service_sensitivity']=dict(core0=read('reports/s3-queue-owner/periodic-runtime.json'),core1=read('reports/s3-queue-owner/timer-core1-runtime.json'),candidate_settings=read('reports/s3-queue-owner/periodic-candidates.json'),headroom=read('reports/s3-queue-owner/periodic-headroom.json'))
    result['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['reports/s3-queue-owner/phy-periodic.json','reports/s3-queue-owner/periodic-runtime.json','reports/s3-queue-owner/timer-core1-runtime.json','reports/s3-queue-owner/periodic-candidates.json','reports/s3-queue-owner/periodic-headroom.json','reports/s3-queue-owner/lifetime-memory.json','reports/s3-queue-owner/allocations.json','reports/s3-queue-owner/runtime.json','reports/s3-queue-owner/instructions.json','reports/s3-queue-owner/memory.json','reports/s3-queue-study/inline-runtime.json','reports/s3-inline-packing/slice-costs.json','reports/s3-queue-study/audited-runtime.json','reports/s3-queue-study/sdk-n16r8/costs.json','reports/s3-queue-study/sdk/audit.json','reports/s3-queue-study/runtime.json','reports/s3-queue-study/extended.json','reports/s3-inline-packing/instructions.json','reports/s3-tx-idle-study/results.json','reports/s3-counter-envelope/instructions.json','reports/s3-counter-envelope/runtime.json','reports/s3-wait-cost/instructions.json','reports/s3-wait-cost/runtime.json','reports/s3-owner-order-estimate/results.json','reports/s3-receiver-application-inventory/README.md','reports/s3-receiver-cost-ledger/instructions.json','reports/s3-receiver-cost-ledger/tick.json','reports/s3-receiver-cost-ledger/irq-entry.json','reports/s3-receiver-cost-ledger/runtime.json','reports/s3-sdk-cost-ledger/results.json','reports/s3-sdk-cost-ledger/runtime.json','reports/s3-joint-runtime/results.json','reports/s3-cost-reconciliation/results.json','reports/s3-owner-iteration-path/results.json','reports/s3-owner-quiet-path/results.json','experiments/s3_integrated_estimate.py','ci/s3_pack_path_audit.py','experiments/s3_native_capture.c','reports/s3-budgeted-fill/u8/target.json','reports/s3-spi-running-guard/cfg-S/results.json','reports/s3-spi-running-guard/cfg-T/results.json','reports/s3-spi-running-guard/sdk-S/sdk-verification.json','reports/partition-recheck-20261023/recomputed-k7-resource-variants.json','reports/controller-cursor-mask/pnr.json.gz','reports/cursor-mask-route-comparison/audit.json','reports/cursor-mask-timingweight20/result.json','reports/cursor-mask-timingweight10-seed2/result.json','reports/s3-preprocess-break-even/qacc/qacc-audit.json']}
    (OUT/'estimate.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(cpu=[{k:v for k,v in r.items() if k!='cases'} for r in cpu],FIR_saved=saved,timing=result['partial_timing'],FIR_optimistic=optimistic),indent=2))
if __name__=='__main__':main()

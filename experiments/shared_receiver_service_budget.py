"""Diagnostic ownership overlay for measured joint variants; no whole receiver qualification."""
import hashlib,json
from pathlib import Path
r=Path(__file__).resolve().parents[1]
variants=[]
for name in ['','-buffered','-elastic','-isolated','-isolated-seed2','-metadata','-metadata-retry','-refresh-predecode']:
 p=r/('reports/shared-receiver-refresh-predecode-evidence/summary.json' if name=='-refresh-predecode' else f'reports/shared-receiver-service{name}-evidence/summary.json')
 if not p.exists():raise SystemExit('CAD still running: '+str(p))
 d=json.loads(p.read_text());fmax=next(iter(d.get('fmax',{}).values()),{}).get('achieved')
 measured={k:d.get(k)for k in ['logic_with_ram_blockers','FF_sites_with_ram_blockers','BSRAM','DSP18','RAM16SDP4','pnr_exit','route_completed','partial_target_pass']};measured['reported_fmax_MHz']=fmax
 # Resource overlay records the measured netlist only; not whole P&R success.
 mix=None
 if measured['logic_with_ram_blockers'] is not None:
  mix=dict(logic=19891-3854-7468+measured['logic_with_ram_blockers'],FF_sites=11759-1481-3528+measured['FF_sites_with_ram_blockers'],BSRAM=43-0-5+measured['BSRAM'],DSP18=34-0-2+measured['DSP18'])
  mix['occupancy_percent']={k:100*mix[k]/v for k,v in [('logic',20736),('FF_sites',15552),('BSRAM',46),('DSP18',48)]}
  mix['margins']={k:v-mix[k] for k,v in [('logic',20736),('FF_sites',15552),('BSRAM',46),('DSP18',48)]}
  mix['logic_margin']=20736-mix['logic'];mix['resource_only_within_capacity']=all(mix[k]<=v for k,v in [('logic',20736),('FF_sites',15552),('BSRAM',46),('DSP18',48)])
 variants.append(dict(name='original'if not name else name[1:],evidence=str(p.relative_to(r)),measured_partial=measured,mixed_diagnostic=mix,adopted=False,response_capture_bits=0 if not name else 256,T_elastic_FIFO_words=2 if name=='-elastic' else 0,isolated_depuncture_ready=name in ('-isolated','-isolated-seed2','-metadata','-metadata-retry','-refresh-predecode'),registered_request_metadata_bits=22 if name in ('-metadata','-metadata-retry') else 0))
metadata=json.loads((r/'reports/shared-receiver-service-metadata-test.json').read_text())
isolated=json.loads((r/'reports/shared-receiver-service-isolated-test.json').read_text())
base=json.loads((r/'reports/shared-receiver-service-test.json').read_text());elastic=json.loads((r/'reports/shared-receiver-service-elastic-test.json').read_text())
result=dict(scope='Actual controller/reader + TC8/binary shared K7 + S256 FIFO + optional whole-response and T2-word holding. Other receiver stages remain allocations.',feasibility_status='undetermined',search_stopped=False,all_20k_partitions_impossible_proved=False,whole_receiver_resources=None,whole_receiver_timing_verified=False,whole_receiver_deadlines_verified=False,formally_assigned_routes=0,adopted_receivers=0,variants=variants,source_s_FIFO_capacity=256,S_FIFO_word_bits=32,T_response_capture_bits=256,T_elastic_words=2,T_elastic_word_bits=10,previous_mixed=dict(logic=19891,FF_sites=11759,BSRAM=43,DSP18=34),replacement_scope='Remove service/reader3854 and shared TC8 stage7468 once, insert joint netlist cost. Do not subtract TC8 again.',other_missing_integration_cost_zero=True,other_stages_are_allocations=True,actual_BG_producer_holding_not_implemented=True,actual_S_interleaver_burst_not_implemented=True,source_data_oracle_pass=base['passed_functional_and_data'] and elastic['passed_functional_and_data'] and isolated['passed_functional_and_data'] and metadata['passed_functional_and_data'],original_and_buffered_traces=base['traces'],elastic_traces=elastic['traces'],isolated_ready_traces=isolated['traces'],metadata_traces=metadata['traces'],metadata_cycle_traces_identical_to_isolated=metadata['traces']==isolated['traces'],all_phase_or_long_term_proof=False)
a=json.loads((r/'reports/shared-receiver-service-isolated-evidence/summary.json').read_text())
b=json.loads((r/'reports/shared-receiver-service-isolated-seed2-evidence/summary.json').read_text())
sv=lambda d:{f:h for f,h in d['source_sha256'].items() if f.endswith('.sv')}
assert sv(a)==sv(b), 'Seed comparison must use identical RTL and probe'
result['same_RTL_and_probe_across_seeds']=True
refresh=json.loads((r/'reports/shared-receiver-refresh-predecode-test.json').read_text())
result['refresh_predecode_traces']=refresh['traces']
assert refresh['traces']==isolated['traces']
result['refresh_predecode_cycle_traces_identical_to_isolated']=True
result['selected_for_next_gate']='refresh-predecode' if variants[-1]['measured_partial']['partial_target_pass'] and refresh['all_diagnostic_deadlines_pass'] and variants[-1]['mixed_diagnostic']['resource_only_within_capacity'] else None
result['signal_information_precision_changed']=False
result['software_quality_reduction']=False
result['continuation_reason']='Refresh predecode passes the service/reader/K7 partial target at 156.739807MHz with identical recorded traces. Actual FFT integration is a separate gate; other receiver stages, physical IO, S3 capture/transport and WCET remain unqualified. Normal peripheral S routes fail the high CPU model after driver costs.'
first=json.loads((r/'reports/shared-receiver-service-metadata-evidence/summary.json').read_text())
retry=json.loads((r/'reports/shared-receiver-service-metadata-retry-evidence/summary.json').read_text())
assert first['source_sha256']==retry['source_sha256'], 'Retry must use identical sources and collector'
result['metadata_retry_identical_sources']=True
result['seed2_time_limit_seconds']=600
result['generator_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
(r/'reports/shared-receiver-service-budget.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(variants,indent=2))

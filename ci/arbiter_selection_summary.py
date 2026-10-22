"""Audit the two arbitration rewrites against the frozen receiver baseline."""
import gzip,hashlib,json,math,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
base=json.loads((R/'reports/t-time-tile-dma-onehot-full.json').read_text())
oldroute=json.loads((R/'reports/placement-compatible-pairs-folded-extended/audit.json').read_text())
out={'baseline_commit':'33f93d04f5e733b1cacfe24b2885d09f48d16e41','target_MHz':1080/7,'baseline_routed_MHz':oldroute['routed_MHz'],'baseline_physical_sites':19423,'baseline_pack_lower_bound':19404,'receiver_adopted':False,'qualified_routes':0,'variants':{}}
for tag in ['parallel','matrix','bank']:
 d=R/(f'reports/arbiter-{tag}'if tag!='bank'else'reports/controller-bank-parallel');finite=json.loads((d/'finite.json').read_text());mapped=json.loads((d/'mapped-result.json').read_text());route=json.loads((d/'route-result.json').read_text())
 assert finite['clients']==base['clients']
 assert finite['checked_output_words']==119808 and finite['checked_writes']==29796
 assert finite['all_declared_deadlines_pass'] and finite['tiles']==312 and finite['competition']
 for source,h in {**finite['source_sha256'],**mapped['source_sha256']}.items():assert hashlib.sha256((R/source).read_bytes()).hexdigest()==h,source
 log=d/('verified-contract.log'if tag=='parallel'else'equivalence.log'if tag=='bank'else'equivalence-contract.log')
 text=log.read_text();assert text.count('Equivalence successfully proven!')==(4 if tag=='bank'else 2) and text.rstrip().endswith('OK')
 raw=gzip.decompress((d/'folded.json.gz').read_bytes());assert hashlib.sha256(raw).hexdigest()==route['mapped_sha256']==mapped['folded.json_sha256']
 assert route['binary_sha256']=='d72d2903f4ccf7c569deec4e205356cb661cffdfcd82408dde414ba0b90790ad'
 v=dict(mapped_lower_bound=mapped['full_fixture_bound']['optimistic_logic_site_lower_bound'],FF=mapped['full_fixture_bound']['FF'],finite_clients=finite['clients'],finite_cycle_margin=2566080-finite['clients'][2]['finish'],route=route,formal_equivalence_pass=True)
 if route['route_completed']:
  freq=route['fmax']['dut.clk']['achieved'];delay=sum(route['path_delay_ns_by_type'].values());assert math.isclose(1000/delay,freq,rel_tol=1e-6)
  v.update(routed_MHz=freq,target_pass=freq>=1080/7,K7_minimum_pass=freq>=152.626638,critical_period_ns=delay)
  from ci.gowin_ff_site_audit import audit
  net=json.loads(gzip.decompress((d/'routed.json.gz').read_bytes()));assert audit(net['modules']['top']['cells'])==route['physical_sites']
 v['artifact_sha256']={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [log,d/'finite.json',d/'mapped-result.json',d/'route-result.json',d/'structural-depth.json']}
 out['variants'][tag]=v
paths=['ci/arbiter_selection_summary.py','tests/test_sdram_client_arbiter.py']
for tag in ['parallel','matrix']:
 paths += [f'experiments/sdram_client_arbiter_{tag}.sv',f'experiments/sdram_client_arbiter_{tag}_metadata.sv',f'tests/test_sdram_client_arbiter_{tag}.py',f'tests/test_t_time_tile_dma_{tag}.py',f'ci/arbiter_{tag}_evidence.py',f'ci/arbiter_{tag}_route.py',f'ci/arbiter_{tag}_path_depth.py']
paths += ['experiments/dual_sdram_bank_parallel.sv','tests/test_sdram_bank_parallel.py','tests/test_t_time_tile_dma_bank_parallel.py','ci/controller_bank_parallel_evidence.py','ci/controller_bank_parallel_route.py','ci/controller_bank_parallel_path_depth.py']
out['source_sha256']={p:hashlib.sha256((R/p).read_bytes()).hexdigest()for p in paths}
(R/'reports/continuation-20261022c.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:{n:v[n]for n in ['mapped_lower_bound','finite_cycle_margin','routed_MHz','target_pass']if n in v}for k,v in out['variants'].items()},indent=2))

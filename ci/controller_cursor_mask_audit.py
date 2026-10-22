"""Check completed cursor-mask evidence against the routed lookahead baseline."""
import gzip,hashlib,json,math,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from ci.gowin_ff_site_audit import audit
D=R/'reports/controller-cursor-mask'
b=json.loads((R/'reports/controller-client-lookahead/finite.json').read_text())
f=json.loads((D/'finite.json').read_text());m=json.loads((D/'mapped-result.json').read_text());r=json.loads((D/'route-result.json').read_text())
assert f['clients']==b['clients'] and f['tiles']==312 and f['competition']
assert f['checked_output_words']==119808 and f['checked_writes']==29796 and f['all_declared_deadlines_pass']
for path,h in {**f['source_sha256'],**m['source_sha256']}.items():assert hashlib.sha256((R/path).read_bytes()).hexdigest()==h,path
proof=(D/'equivalence.log').read_text();assert proof.count('Equivalence successfully proven!')==2 and proof.rstrip().endswith('OK')
for n in ['mapped.json','prebuffer.json','folded.json','packed.json','prebuffer.identity-proof.json','folded.controls-proof.json']:
 assert hashlib.sha256(gzip.decompress((D/(n+'.gz')).read_bytes())).hexdigest()==m[n+'_sha256'],n
assert r['timeout_seconds'] is None
assert r['mapped_sha256']==m['folded.json_sha256']==hashlib.sha256(gzip.decompress((D/'folded.json.gz').read_bytes())).hexdigest()
assert r['binary_sha256']=='d72d2903f4ccf7c569deec4e205356cb661cffdfcd82408dde414ba0b90790ad'
out={'whole_receiver_verified':False,'receiver_adopted':False,'finite_clients':f['clients'],'finite_margin_cycles':2566080-f['clients'][2]['finish'],'formal_equivalence_pass':True,'mapped_bound':m['full_fixture_bound'],'route':r}
if r['route_completed']:
 raw=gzip.decompress((D/'routed.json.gz').read_bytes());assert hashlib.sha256(raw).hexdigest()==r['routed.json_sha256']
 cells=json.loads(raw)['modules']['top']['cells'];assert audit(cells)==r['physical_sites']
 packed=json.loads(gzip.decompress((D/'packed.json.gz').read_bytes()))['modules']['top']['cells']
 added=set(cells)-set(packed);removed=set(packed)-set(cells)
 assert len(added)==13
 for name in added:
  c=cells[name];assert c['type']=='LUT4' and int(c['parameters']['INIT'],2)==0xff00 and set(c['connections'])=={'I3','F'}
 assert all(packed[n]['type'] in ['BLOCKER_LUT','BLOCKER_FF']for n in removed)
 out['postplace_added_identity_LUTs']=len(added)
 out['removed_blockers']={kind:sum(packed[n]['type']==kind for n in removed)for kind in ['BLOCKER_LUT','BLOCKER_FF']}
 assert r['physical_sites']['packed_logic_with_ram_blockers']==m['full_fixture_bound']['packed_logic_with_ram_blockers']+len(added)
 raw=gzip.decompress((D/'pnr.json.gz').read_bytes());assert hashlib.sha256(raw).hexdigest()==r['pnr.json_sha256']
 report=json.loads(raw);frequency=report['fmax']['dut.clk']['achieved'];delay=sum(r['path_delay_ns_by_type'].values())
 assert math.isclose(1000/delay,frequency,rel_tol=1e-6)
 out.update(routed_MHz=frequency,target_pass=frequency>=1080/7,K7_minimum_pass=frequency>=152.626638,required_cut_ns=max(0,delay-1000/(1080/7)))
 out['longest_routing_arc']=max((a for a in report['critical_paths'][0]['path']if a['type']=='routing'),key=lambda a:a['delay'])
cleanup=json.loads((D/'collector-cleanup.json').read_text())
executed=gzip.decompress((D/'executed-evidence-collector.py.gz').read_bytes())
assert hashlib.sha256(executed).hexdigest()==cleanup['executed_collector_sha256']
assert hashlib.sha256((R/'ci/controller_cursor_mask_evidence.py').read_bytes()).hexdigest()==cleanup['current_collector_sha256']
out['collector_cleanup']=cleanup
paths=['ci/controller_cursor_mask_audit.py','ci/controller_cursor_mask_evidence.py','ci/controller_cursor_mask_route.py','tests/test_sdram_client_arbiter_cursor_mask.py','tests/test_t_time_tile_dma_cursor_mask.py','experiments/sdram_client_arbiter_cursor_mask.sv','experiments/sdram_client_arbiter_cursor_mask_metadata.sv','reports/exploration-stop-policy.md']
paths += [str((D/n).relative_to(R))for n in ['finite.json','mapped-result.json','equivalence.log','route-result.json','route.log']]
out['source_sha256']={p:hashlib.sha256((R/p).read_bytes()).hexdigest()for p in paths}
(D/'audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k not in ['source_sha256','route','finite_clients','longest_routing_arc']},indent=2))

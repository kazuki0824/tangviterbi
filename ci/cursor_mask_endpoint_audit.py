"""Audit endpoint coverage and compare frozen-netlist physical implementations."""
import collections,gzip,hashlib,json,math,re,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from ci.gowin_ff_site_audit import audit
out={'whole_receiver_verified':False,'receiver_adopted':False,'scope':'Modeled synchronous setup endpoints; no external IO or complete receiver proof.','runs':{},'tool_period_ns':int(1e6/(1080/7))/1000,'period_quantization':'Pinned Himbaechel delay_t=int32_t in ps; getDelayFromNS truncates ns*1000.'}
base=R/'reports/controller-cursor-mask'
old=json.loads((base/'route-result.json').read_text())
for seed in [1,2]:
 d=R/f'reports/cursor-mask-endpoints-seed{seed}'
 r=json.loads((d/'route-result.json').read_text());assert r['route_completed'] and r['timeout_seconds']is None
 assert r['mapped_sha256']==old['mapped_sha256'];assert r['chipdb_sha256']==old['chipdb_sha256']
 text=(d/'route.log').read_text();coverage={};ends={}
 for domain,clock,total,failing in re.findall(r'Endpoint coverage domain=(\d+) clock=(\S+) total=(\d+) failing=(\d+)',text):
  value=dict(clock=clock,total=int(total),failing=int(failing));assert domain not in coverage or coverage[domain]==value;coverage[domain]=value
 for domain,rank,cell,port,slack in re.findall(r'Endpoint diagnostic domain=(\d+) rank=(\d+) cell=(\S+) port=(\S+) setup_slack_ns=([-\d.]+)',text):
  value=dict(rank=int(rank),cell=cell,port=port,slack_ns=float(slack));key=(domain,int(rank));assert key not in ends or ends[key]==value;ends[key]=value
 assert coverage
 net=json.loads(gzip.decompress((d/'routed.json.gz').read_bytes()));cells=net['modules']['top']['cells'];assert audit(cells)==r['physical_sites']
 report=json.loads(gzip.decompress((d/'pnr.json.gz').read_bytes()))
 paths={}
 for p in report['critical_paths']:
  arcs=p['path'];endpoint=(arcs[-1]['to']['cell'],arcs[-1]['to']['port']);paths[endpoint]=arcs
 negatives=[]
 for domain,c in coverage.items():
  e=sorted([v for (dm,rank),v in ends.items()if dm==domain],key=lambda v:v['rank'])
  assert len(e)==min(c['total'],max(32,c['failing']))
  assert [x['rank']for x in e]==list(range(1,len(e)+1))
  assert sum(x['slack_ns']<0 for x in e)==c['failing']
  for x in e:
   if x['slack_ns']>=0:continue
   arcs=paths[(x['cell'],x['port'])];delay=sum(a['delay']for a in arcs)
   # This fixture has one rising-edge same-clock domain; check rather than assume.
   assert all(p['from']=='posedge dut.clk'and p['to']=='posedge dut.clk'for p in report['critical_paths'])
   assert math.isclose(int(1e6/(1080/7))/1000-delay,x['slack_ns'],abs_tol=2e-6)
   kinds=collections.Counter(cells[a['to']['cell']]['type']for a in arcs if a['type']=='logic')
   negatives.append(dict(x,domain=domain,delay_ns=delay,launch=arcs[0]['from'],logic_cell_types=dict(kinds),longest_wire=max((a for a in arcs if a['type']=='routing'),key=lambda a:a['delay'])))
 f=r['fmax']['dut.clk']['achieved'];assert math.isclose(1000/sum(r['path_delay_ns_by_type'].values()),f,rel_tol=1e-6)
 run={'route':r,'endpoint_coverage':coverage,'negative_endpoints':negatives,'target_pass':f>=1080/7,'K7_minimum_pass':f>=152.626638}
 if seed==1:
  assert r['fmax']==old['fmax'] and r['physical_sites']==old['physical_sites']
  bn=json.loads(gzip.decompress((base/'routed.json.gz').read_bytes()))
  diagnostic_setting=net['modules']['top']['settings'].pop('diagnostics/final_report')
  assert net['modules']==bn['modules'],'Diagnostic rerun changed routed graph or other settings'
  run['same_routed_modules_except_diagnostic_setting']=True
  run['diagnostic_setting_value']=diagnostic_setting
 run['source_sha256']={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [d/'route-result.json',d/'route.log',d/'pnr.json.gz',d/'routed.json.gz']}
 out['runs'][str(seed)]=run
out['script_sha256']={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [R/'ci/cursor_mask_endpoint_audit.py',R/'ci/cursor_mask_endpoint_route.py',R/'ci/patch_nextpnr_failing_endpoints.py']}
(R/'reports/cursor-mask-endpoints-audit.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:{'MHz':v['route']['fmax']['dut.clk']['achieved'],'negative_endpoints':len(v['negative_endpoints']),'target_pass':v['target_pass']}for k,v in out['runs'].items()},indent=2))

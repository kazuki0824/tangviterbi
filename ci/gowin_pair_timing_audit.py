"""Audit estimated timing arithmetic, added LUTs, and unchanged diagnostic placement."""
import collections,gzip,hashlib,json,math
from pathlib import Path
from ci.gowin_ff_site_audit import audit
R=Path(__file__).resolve().parents[1]
def read(p):
 if p.exists():return json.loads(p.read_bytes())
 return json.loads(gzip.decompress(Path(str(p)+'.gz').read_bytes()))
def cells(x):return next(iter(x['modules'].values()))['cells']
result={'routed_timing':False,'target_period_ns':1000/(1080/7),'runs':{}}
for name,directory,placed,packed,expected in [('prebuffer','placement-compatible-pairs-timing','diagnostic-placed.json','placement-compatible-pairs/paired-packed.json',48),('folded','placement-compatible-pairs-folded-timing','placed.json','placement-compatible-pairs/folded-graph/paired-packed.json',19)]:
 d=R/'reports'/directory;t=read(d/'timing.json');p=read(d/placed);pc=cells(p);ac=cells(read(R/'reports'/packed));new=sorted(set(pc)-set(ac));assert set(ac)<=set(pc) and len(new)==expected
 for n in new:
  c=pc[n];assert n.endswith('_passthrough_lut$') and c['type']=='LUT4' and int(c['parameters']['INIT'],2)==0xff00 and set(c['connections'])=={'I3','F'}
 path=t['critical_paths'][0]['path'];s=collections.Counter()
 for arc in path:s[arc['type']]+=arc['delay']
 total=sum(s.values());assert math.isclose(1000/total,t['fmax']['dut.clk']['achieved'],rel_tol=1e-6)
 r={'estimated_MHz':t['fmax']['dut.clk']['achieved'],'delay_ns_by_type':dict(s),'cell_only_ns_for_this_path':sum(s[k]for k in ('clk-to-q','logic','setup')),'logic_stages':sum(x['type']=='logic'for x in path),'launch':path[0]['from'],'capture':path[-1]['to'],'new_identity_LUT_count':len(new),'post_placement_audit':audit(pc)}
 assert r['post_placement_audit']['packed_logic_with_ram_blockers']==t['utilization']['LUT4']['used']==19404+expected
 if name=='prebuffer':
  reference=read(R/'reports/placement-compatible-pairs-checkpoint/placed.json');a=next(iter(reference['modules'].values()));b=next(iter(p['modules'].values()));r['diagnostic_placement_unchanged']={k:a[k]==b[k]for k in ('cells','ports','netnames')};assert all(r['diagnostic_placement_unchanged'].values())
 result['runs'][name]=r
result['warning']='Cell-only numbers concern the reported estimated worst path, not the maximum of all zero-wire paths. Clock skew/routing numbers are predictions before routing. No whole-receiver timing pass.'
result['source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
(R/'reports/placement-compatible-pairs-timing/comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

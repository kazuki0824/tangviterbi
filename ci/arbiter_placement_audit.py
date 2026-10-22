"""Check placed resource counts and identity additions independently of mapped budgets."""
import collections,gzip,hashlib,json,math,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from ci.gowin_ff_site_audit import audit
out={}
for label in ['arbiter-parallel','arbiter-matrix','controller-bank-parallel']:
 d=R/'reports'/label;p=d/'placement-timing'
 a=json.loads(gzip.decompress((d/'packed.json.gz').read_bytes()))['modules']['top']['cells']
 b=json.loads(gzip.decompress((p/'placed.json.gz').read_bytes()))['modules']['top']['cells']
 r=json.loads((p/'result.json').read_text());t=json.loads(gzip.decompress((p/'timing.json.gz').read_bytes()))
 new=sorted(set(b)-set(a));assert set(a)<=set(b)
 for n in new:
  c=b[n];assert n.endswith('_passthrough_lut$') and c['type']=='LUT4' and int(c['parameters']['INIT'],2)==0xff00 and set(c['connections'])=={'I3','F'}
  assert all(((0xff00>>i)&1)==((i>>3)&1)for i in range(16))
 assert r['exit']==0 and not r['routed'];assert audit(b)==r['physical_sites']
 used=r['physical_sites']['packed_logic_with_ram_blockers'];assert used==t['utilization']['LUT4']['used']==audit(a)['packed_logic_with_ram_blockers']+len(new)
 assert math.isclose(1000/sum(r['predicted_path_delay_ns_by_type'].values()),t['fmax']['dut.clk']['achieved'],rel_tol=1e-6)
 out[label]={'positions':used,'added_identity_LUTs':len(new),'positions_percent':100*used/20736,'FF':audit(b)['FF'],'predicted_MHz':t['fmax']['dut.clk']['achieved'],'routed_MHz':None,'cell_delay_on_predicted_path_ns':sum(r['predicted_path_delay_ns_by_type'].get(k,0)for k in ['clk-to-q','logic','setup']),'logic_stages_on_predicted_path':r['logic_stages'],'source_sha256':{str(q.relative_to(R)):hashlib.sha256(q.read_bytes()).hexdigest()for q in [p/'result.json',p/'placed.json.gz',p/'timing.json.gz']}}
(R/'reports/arbiter-placement-timing/audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

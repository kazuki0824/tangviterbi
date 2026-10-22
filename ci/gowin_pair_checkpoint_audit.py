"""Check post-placement resource growth independently of the pack-only bound."""
import gzip,json
from pathlib import Path
from ci.gowin_ff_site_audit import audit
ROOT=Path(__file__).resolve().parents[1];d=ROOT/'reports/placement-compatible-pairs-checkpoint'
def read(p):return json.loads(gzip.decompress(p.read_bytes()))
a=next(iter(read(ROOT/'reports/placement-compatible-pairs/paired-packed.json.gz')['modules'].values()))['cells']
b=next(iter(read(d/'placed.json.gz')['modules'].values()))['cells'];report=read(d/'placement-report.json.gz')
new=sorted(set(b)-set(a));assert set(a)<=set(b)
assert len(new)==48 and all(n.endswith('_passthrough_lut$') for n in new)
for n in new:
 c=b[n];assert c['type']=='LUT4' and int(c['parameters']['INIT'],2)==0xff00
 assert set(c['connections'])=={'I3','F'}
 # With the unused I0-I2 inputs, ff00 is identity for every possible input state.
 for address in range(16):assert ((0xff00>>address)&1)==((address>>3)&1)
r={'before':audit(a),'after':audit(b),'added_identity_LUTs':new,'added_count':len(new),'reported_utilization':report['utilization'],'critical_paths_available':bool(report['critical_paths']),'routed':False,'placement_clock_is_estimated':True}
assert r['after']['packed_logic_with_ram_blockers']==report['utilization']['LUT4']['used']==19452
assert r['after']['FF']==r['before']['FF']==8662
assert r['after']['minimum_extra_passthrough_LUTs']==0
(d/'audit.json').write_text(json.dumps(r,indent=2)+'\n');print({k:r[k]for k in ('added_count','critical_paths_available','routed')})

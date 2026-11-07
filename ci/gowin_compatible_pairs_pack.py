import subprocess,json,gzip,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1];w=r.parent;d=r/'reports/placement-compatible-pairs'
source='placement-dynamic-prebuffer'
if '--folded' in sys.argv:
 source='placement-dynamic-folded-controls';d=d/'folded-graph';d.mkdir(exist_ok=True)
for name,b in [('control','nextpnr-control'),('paired','nextpnr-himbaechel')]:
 cmd=[str(w/'nextpnr-build'/b),'--json',str(r/'reports'/source/'mapped.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt','cst='+str(r/'reports/placement-dynamic-prebuffer/pins.cst'),'--pack-only','--write',str(d/(name+'-packed.json'))]
 with (d/(name+'-pack.log')).open('w')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
 x=json.loads((d/(name+'-packed.json')).read_text());print(name,list(x));

a=json.loads((d/'control-packed.json').read_text());b=json.loads((d/'paired-packed.json').read_text())
ma=next(iter(a['modules'].values()));mb=next(iter(b['modules'].values()))
import hashlib
result={k+'_identical':ma[k]==mb[k] for k in ('cells','ports','netnames')}
assert all(result.values())
result['cell_count']=len(ma['cells'])
result['note']='Cluster metadata is not serialized; this checks graph preservation, not legal placement.'
for name in ('control','paired'):
 p=d/(name+'-packed.json');result[name+'_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
 (d/(name+'-packed.json.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0));p.unlink()
(d/'graph-comparison.json').write_text(json.dumps(result,indent=2)+'\n')

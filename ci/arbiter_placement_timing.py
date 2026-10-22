"""Independent normal pack/place for diagnostics; predictions are not routed STA."""
import collections,gzip,hashlib,json,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from ci.gowin_ff_site_audit import audit
for label in sys.argv[1:]:
 source=R/'reports'/label;d=source/'placement-timing';d.mkdir(exist_ok=True)
 cmd=json.loads((source/'route-command.json').read_text());cmd[0]=str(R.parent/'nextpnr-build/nextpnr-checkpoint-timing')
 for opt,name in [('--report','timing.json'),('--write','placed.json')]:cmd[cmd.index(opt)+1]=str(d/name)
 cmd+=['--no-route','--timing-allow-fail'];(d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 r={'routed':False,'input_sha256':hashlib.sha256(Path(cmd[cmd.index('--json')+1]).read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(Path(cmd[0]).read_bytes()).hexdigest()};start=time.monotonic()
 with (d/'timing.log').open('w')as f:
  try:r['exit']=subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT,timeout=600).returncode
  except subprocess.TimeoutExpired:r['exit']='timeout'
 r['seconds']=time.monotonic()-start
 if (d/'timing.json').exists():
  t=json.loads((d/'timing.json').read_text());r['fmax_estimated']=t.get('fmax');path=t['critical_paths'][0]['path'];s=collections.Counter()
  for arc in path:s[arc['type']]+=arc['delay']
  r.update(predicted_path_delay_ns_by_type=dict(s),launch=path[0]['from'],capture=path[-1]['to'],logic_stages=sum(x['type']=='logic'for x in path))
 if (d/'placed.json').exists():
  c=json.loads((d/'placed.json').read_text())['modules']['top']['cells'];r['physical_sites']=audit(c)
 for name in ['timing.json','placed.json']:
  p=d/name
  if p.exists():r[name+'_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();(d/(name+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0))
 (d/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(label,json.dumps(r),flush=True)

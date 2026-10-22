"""Estimate folded-control placement timing; no routed timing claim."""
import gzip,hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];d=R/'reports/placement-compatible-pairs-folded-timing';d.mkdir(exist_ok=True)
cmd=json.loads((R/'reports/placement-compatible-pairs/folded-command.json').read_text());cmd[0]=str(R.parent/'nextpnr-build/nextpnr-checkpoint-timing')
for opt,name in [('--report','timing.json'),('--write','placed.json')]:cmd[cmd.index(opt)+1]=str(d/name)
cmd+=['--no-route','--timing-allow-fail'];(d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
r={'routed':False,'input_sha256':hashlib.sha256(Path(cmd[cmd.index('--json')+1]).read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(Path(cmd[0]).read_bytes()).hexdigest()}
start=time.monotonic()
with (d/'timing.log').open('w')as f:
 try:code=subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT,timeout=600).returncode
 except subprocess.TimeoutExpired:code='timeout'
r.update(exit=code,seconds=time.monotonic()-start)
for name in ('timing.json','placed.json'):
 p=d/name
 if p.exists():r[name+'_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();(d/(name+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0));p.unlink()
(d/'run.json').write_text(json.dumps(r,indent=2)+'\n');print(r,flush=True)

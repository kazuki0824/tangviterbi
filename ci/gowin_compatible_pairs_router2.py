"""Try router2 on the folded fixture; all hardware legality and target timing retained."""
import gzip,hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];d=R/'reports/placement-compatible-pairs-router2';d.mkdir(exist_ok=True)
cmd=json.loads((R/'reports/placement-compatible-pairs/folded-command.json').read_text())
for opt,name in [('--report','pnr.json'),('--write','routed.json')]:cmd[cmd.index(opt)+1]=str(d/name)
cmd+=['--router','router2'];(d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
r={'router':'router2','timeout_seconds':1800,'whole_receiver_verified':False,'input_sha256':hashlib.sha256(Path(cmd[cmd.index('--json')+1]).read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(Path(cmd[0]).read_bytes()).hexdigest()}
start=time.monotonic()
with (d/'route.log').open('w')as f:
 try:code=subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT,timeout=1800).returncode
 except subprocess.TimeoutExpired:code='timeout'
r.update(exit=code,seconds=time.monotonic()-start)
log=(d/'route.log').read_text();r['errors']=[x for x in log.splitlines()if x.startswith('ERROR:')];r['route_completed']='Routing complete.'in log
for name in ('pnr.json','routed.json'):
 p=d/name
 if p.exists():r[name+'_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();(d/(name+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0));p.unlink()
(d/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(r,flush=True)

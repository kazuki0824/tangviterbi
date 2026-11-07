"""Repeat the progressing folded route with an explicit 1800-second bound."""
import hashlib,json,os,re,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
d=ROOT/'reports/placement-compatible-pairs-folded-extended';d.mkdir(exist_ok=True)
base=ROOT/'reports/placement-compatible-pairs'
cmd=json.loads((base/'folded-command.json').read_text())
for opt,filename in [('--report','pnr.json'),('--write','routed.json')]:cmd[cmd.index(opt)+1]=str(d/filename)
(d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
r={'timeout_seconds':1800,'original_timeout_seconds':600,'target_MHz':154.28571428571428,'binary_sha256':hashlib.sha256(Path(cmd[0]).read_bytes()).hexdigest(),'mapped_sha256':hashlib.sha256(Path(cmd[cmd.index('--json')+1]).read_bytes()).hexdigest(),'whole_receiver_verified':False}
start=time.monotonic()
with (d/'route.log').open('w')as f:
 try:code=subprocess.run(cmd,cwd=ROOT,env=dict(os.environ,TANG_DIAG_TARGET='dut.bg_address_DFFRE_Q_60'),stdout=f,stderr=subprocess.STDOUT,timeout=1800).returncode
 except subprocess.TimeoutExpired:code='timeout'
log=(d/'route.log').read_text();r.update(exit=code,seconds=time.monotonic()-start,route_completed='Routing complete.'in log,errors=[x for x in log.splitlines()if x.startswith('ERROR:')],frequencies=re.findall(r'Max frequency.*',log))
(d/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)

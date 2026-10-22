"""Save a placement checkpoint and estimated critical paths; not routed timing."""
import gzip,hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];d=ROOT/'reports/placement-compatible-pairs-checkpoint';d.mkdir(exist_ok=True)
cmd=json.loads((ROOT/'reports/placement-compatible-pairs/prebuffer-command.json').read_text())
for opt,filename in [('--report','placement-report.json'),('--write','placed.json')]:cmd[cmd.index(opt)+1]=str(d/filename)
cmd+=['--no-route','--timing-allow-fail']
(d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
start=time.monotonic()
with (d/'placement.log').open('w')as f:
 try:code=subprocess.run(cmd,cwd=ROOT,env=dict(os.environ,TANG_DIAG_TARGET='dut.fft.active_mode_DFFE_Q'),stdout=f,stderr=subprocess.STDOUT,timeout=600).returncode
 except subprocess.TimeoutExpired:code='timeout'
r={'exit':code,'seconds':time.monotonic()-start,'routed':False,'timing_allow_fail_used_only_to_save_checkpoint':True,'binary_sha256':hashlib.sha256(Path(cmd[0]).read_bytes()).hexdigest()}
for n in ('placed.json','placement-report.json'):
 p=d/n
 if p.exists():
  r[n+'_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();(d/(n+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0));p.unlink()
(d/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(r,flush=True)

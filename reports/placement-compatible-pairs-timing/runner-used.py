"""Extract estimated timing from a saved placement using the diagnostic-only reader."""
import gzip,hashlib,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'reports/placement-compatible-pairs-timing';P=ROOT/'reports/placement-compatible-pairs-checkpoint'
(D/'placed.json').write_bytes(gzip.decompress((P/'placed.json.gz').read_bytes()))
cmd=json.loads((ROOT/'reports/placement-compatible-pairs/prebuffer-command.json').read_text())
cmd[0]=str(ROOT.parent/'nextpnr-build/nextpnr-checkpoint-timing')
for opt,name in [('--report','timing.json'),('--write','diagnostic-placed.json')]:cmd[cmd.index(opt)+1]=str(D/name)
cmd+=['--no-route','--timing-allow-fail']
(D/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
start=time.monotonic()
with (D/'timing.log').open('w')as f:r=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=600)
(D/'run.json').write_text(json.dumps({'exit':r.returncode,'seconds':time.monotonic()-start,'routed':False,'input_sha256':hashlib.sha256((D/'placed.json').read_bytes()).hexdigest()},indent=2)+'\n');print(r.returncode)

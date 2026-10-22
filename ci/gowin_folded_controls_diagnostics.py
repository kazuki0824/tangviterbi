"""Classify the remaining rejection after control folding, without rule changes."""
import gzip,hashlib,json,os,re,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 src=ROOT/'reports/shared-receiver-fft-tile-folded-controls-route';d=ROOT/'reports/placement-dynamic-folded-controls';d.mkdir(exist_ok=True)
 (d/'mapped.json').write_bytes(gzip.decompress((src/'mapped.json.gz').read_bytes()));(d/'pins.cst').write_bytes((src/'pins.cst').read_bytes())
 proof=json.loads((src/'mapped.controls-proof.json').read_text());target=next(x['ff']for x in proof['records']if x['lut']=='ff_input_identity_57')
 cmd=json.loads((src/'command.json').read_text());cmd=[x.replace(str(src),str(d))for x in cmd];binary=ROOT.parent/'nextpnr-build/nextpnr-himbaechel';cmd[0]=str(binary)
 (d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n');start=time.monotonic()
 with (d/'pnr.log').open('w')as f:
  try:code=subprocess.run(cmd,cwd=ROOT,env=dict(os.environ,TANG_DIAG_TARGET=target),stdout=f,stderr=subprocess.STDOUT,timeout=600).returncode
  except subprocess.TimeoutExpired:code='timeout'
 log=(d/'pnr.log').read_text();counts={k:dict(all=int(n),target=int(t))for k,n,t in re.findall(r'TANG_REJECT (\w+) all=(\d+) target=(\d+)',log)}
 result=dict(target_FF=target,exit=code,seconds=time.monotonic()-start,counters=counts,errors=[x for x in log.splitlines()if x.startswith('ERROR:')],binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),mapped_sha256=hashlib.sha256((d/'mapped.json').read_bytes()).hexdigest(),source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in ['ci/gowin_folded_controls_diagnostics.py','ci/patch_gowin_placement_targeted.py']})
 reference=json.loads((src/'summary.json').read_text());result['same_failure_as_official']=result['errors']==reference['errors']and code==reference['pnr_exit']
 (d/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));assert result['same_failure_as_official']and len(counts)==15
if __name__=='__main__':main()

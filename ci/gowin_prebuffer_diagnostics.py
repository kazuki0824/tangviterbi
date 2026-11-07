"""Diagnose the paired LUT/receiver-FF failure on the unchanged prebuffer netlist."""
import gzip,hashlib,json,os,re,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WORK=ROOT.parent

def main():
 src=ROOT/'reports/shared-receiver-fft-tile-onehot-prebuffer-route';d=ROOT/'reports/placement-dynamic-prebuffer';d.mkdir(exist_ok=True)
 (d/'mapped.json').write_bytes(gzip.decompress((src/'mapped.json.gz').read_bytes()))
 (d/'pins.cst').write_bytes((src/'pins.cst').read_bytes())
 base=json.loads((src/'command.json').read_text());base=[x.replace(str(src),str(d))for x in base]
 target='dut.fft.active_mode_DFFE_Q'
 result=dict(target_FF=target,scope=__doc__,mapped_sha256=hashlib.sha256((d/'mapped.json').read_bytes()).hexdigest(),runs={})
 for name,binary in [('official',WORK/'toolchain/oss-cad-suite/bin/nextpnr-himbaechel'),('instrumented',WORK/'nextpnr-build/nextpnr-himbaechel')]:
  cmd=[str(binary),*base[1:]];(d/(name+'-command.json')).write_text(json.dumps(cmd,indent=2)+'\n')
  start=time.monotonic()
  with (d/(name+'.log')).open('w')as f:
   try:code=subprocess.run(cmd,cwd=ROOT,env=dict(os.environ,TANG_DIAG_TARGET=target),stdout=f,stderr=subprocess.STDOUT,timeout=300).returncode
   except subprocess.TimeoutExpired:code='timeout'
  log=(d/(name+'.log')).read_text();counts={k:dict(all=int(n),target=int(t))for k,n,t in re.findall(r'TANG_REJECT (\w+) all=(\d+) target=(\d+)',log)}
  result['runs'][name]=dict(exit=code,seconds=time.monotonic()-start,binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),errors=[x for x in log.splitlines()if x.startswith('ERROR:')],counters=counts,route_completed='Routing complete.'in log)
  (d/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(name,code,flush=True)
 result['same_failure']=len({json.dumps([r['exit'],r['errors']])for r in result['runs'].values()})==1
 result['source_sha256']={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in ['ci/gowin_prebuffer_diagnostics.py','ci/patch_gowin_placement_targeted.py']}
 result['whole_receiver_verified']=False
 (d/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
 assert result['same_failure'] and len(result['runs']['instrumented']['counters'])==15
if __name__=='__main__':main()

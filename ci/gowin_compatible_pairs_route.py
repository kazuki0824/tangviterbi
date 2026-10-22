"""Try compatible LUT/FF double clusters, without changing the input graph."""
import hashlib,json,os,re,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; WORK=ROOT.parent

def main():
 d=ROOT/'reports/placement-compatible-pairs'; d.mkdir(exist_ok=True)
 binary=WORK/'nextpnr-build/nextpnr-himbaechel'
 result={'whole_receiver_verified':False,'runs':{},'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
 for name,source,target in [('prebuffer','placement-dynamic-prebuffer','dut.fft.active_mode_DFFE_Q'),('folded','placement-dynamic-folded-controls','dut.bg_address_DFFRE_Q_60')]:
  src=ROOT/'reports'/source
  base=json.loads((ROOT/'reports/placement-dynamic-prebuffer/official-command.json').read_text())
  cmd=[str(binary),*base[1:]]
  cmd[cmd.index('--json')+1]=str(src/'mapped.json')
  for option,filename in [('--report',name+'-pnr.json'),('--write',name+'-routed.json')]:cmd[cmd.index(option)+1]=str(d/filename)
  (d/(name+'-command.json')).write_text(json.dumps(cmd,indent=2)+'\n')
  start=time.monotonic()
  with (d/(name+'.log')).open('w')as f:
   try:code=subprocess.run(cmd,cwd=ROOT,env=dict(os.environ,TANG_DIAG_TARGET=target),stdout=f,stderr=subprocess.STDOUT,timeout=600).returncode
   except subprocess.TimeoutExpired:code='timeout'
  log=(d/(name+'.log')).read_text()
  result['runs'][name]={'exit':code,'seconds':time.monotonic()-start,'target':target,'mapped_sha256':hashlib.sha256((src/'mapped.json').read_bytes()).hexdigest(),'errors':[x for x in log.splitlines()if x.startswith('ERROR:')],'clusters':re.findall(r'TANG compatible double LUTFF clusters: (\d+)',log),'counters':{k:dict(all=int(a),target=int(t))for k,a,t in re.findall(r'TANG_REJECT (\w+) all=(\d+) target=(\d+)',log)},'route_completed':'Routing complete.'in log}
  (d/'result.json').write_text(json.dumps(result,indent=2)+'\n'); print(name,code,flush=True)
 result['source_sha256']={str(p.relative_to(WORK)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path(__file__),ROOT/'ci/patch_gowin_compatible_pairs.py',WORK/'nextpnr-source/himbaechel/uarch/gowin/pack_luts.cc',WORK/'nextpnr-source/himbaechel/uarch/gowin/gowin.cc']}
 (d/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()

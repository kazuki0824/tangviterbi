"""Compare source-built control/instrumented placement with saved official run."""
import argparse,gzip,hashlib,json,os,re,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--control',type=Path,required=True);p.add_argument('--instrumented',type=Path,required=True);p.add_argument('--chipdb',type=Path,required=True);a=p.parse_args()
 d=ROOT/'reports/placement-dynamic-audit';d.mkdir(exist_ok=True)
 base=json.loads((d/'official-command.json').read_text())
 expected=gzip.decompress((ROOT/'reports/shared-receiver-fft-tile-onehot-route/mapped.json.gz').read_bytes())
 assert (d/'mapped.json').read_bytes()==expected
 result=dict(scope=__doc__,mapped_sha256=digest(d/'mapped.json'),chipdb_sha256=digest(a.chipdb),runs={})
 for name,binary in [('official',Path(base[0])),('control',a.control.resolve()),('instrumented',a.instrumented.resolve())]:
  cmd=[str(binary),*base[1:]]
  (d/(name+'-command.json')).write_text(json.dumps(cmd,indent=2)+'\n')
  if name=='official':
   code=json.loads((d/'official-result.json').read_text())['exit'];seconds=None
  else:
   start=time.monotonic()
   with (d/(name+'.log')).open('w')as f:
    try:code=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=300).returncode
    except subprocess.TimeoutExpired:code='timeout'
   seconds=time.monotonic()-start
  log=(d/(name+'.log')).read_text()
  errors=[x for x in log.splitlines()if x.startswith('ERROR:')]
  counts={k:dict(all=int(all_n),target=int(target_n))for k,all_n,target_n in re.findall(r'TANG_REJECT (\w+) all=(\d+) target=(\d+)',log)}
  result['runs'][name]=dict(exit=code,seconds=seconds,binary_sha256=digest(binary),errors=errors,counters=counts,route_completed='Routing complete.'in log)
  (d/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
  print(name,code,errors,flush=True)
 result['same_failure']=len({json.dumps([r['exit'],r['errors']])for r in result['runs'].values()})==1
 result['source_sha256']={f:digest(ROOT/f)for f in ['ci/gowin_placement_diagnostics.py','ci/patch_gowin_placement_counters.py']}
 result['whole_receiver_verified']=False
 (d/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
 assert result['same_failure'],result
 assert len(result['runs']['instrumented']['counters'])==15,result
if __name__=='__main__':main()

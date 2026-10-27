"""Normal pack/place/route with restored compatible pairs and higher timing weight."""
import argparse,gzip,hashlib,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from ci.gowin_ff_site_audit import audit
def main():
 p=argparse.ArgumentParser();p.add_argument('--nextpnr',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--cad',type=Path,required=True);p.add_argument('--weight',type=int,default=20);p.add_argument('--seed',type=int,default=1);a=p.parse_args()
 suffix=f'cursor-mask-timingweight{a.weight}'+(f'-seed{a.seed}' if a.seed!=1 else '')
 out=ROOT/'reports'/suffix;out.mkdir(exist_ok=True);work=ROOT/'build'/suffix;work.mkdir(exist_ok=True)
 digest=lambda b:hashlib.sha256(b).hexdigest()
 original=ROOT/'reports/controller-cursor-mask';meta=json.loads((original/'route-result.json').read_text());mapped=gzip.decompress((original/'folded.json.gz').read_bytes());assert digest(mapped)==meta['mapped_sha256'];(work/'folded.json').write_bytes(mapped)
 source=a.source.resolve();cad=a.cad.resolve();binary=a.nextpnr.resolve()
 assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()=='e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641'
 assert set(subprocess.check_output(['git','-C',str(source),'diff','--name-only'],text=True).splitlines())==set(meta['backend_source_sha256'])
 for f,h in meta['backend_source_sha256'].items():assert digest((source/f).read_bytes())==h
 db=cad/'share/nextpnr/himbaechel/gowin/chipdb-GW2A-18C.bin';assert digest(db.read_bytes())==meta['chipdb_sha256']
 cmd=[str(binary),'--json',str(work/'folded.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt','cst='+str(original/'pins.cst'),'--freq',str(1080/7),'--seed',str(a.seed),'--placer','heap','--placer-heap-cell-placement-timeout','1000000','--placer-heap-timingweight',str(a.weight),'--router','router1','--report',str(out/'pnr.json'),'--write',str(work/'routed.json')]
 (out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 result=dict(scope=__doc__,mapped_sha256=digest(mapped),backend_source_sha256=meta['backend_source_sha256'],binary_sha256=digest(binary.read_bytes()),chipdb_sha256=meta['chipdb_sha256'],timing_weight=a.weight,seed=a.seed,baseline_timing_weight=10,baseline_seed=1,whole_receiver_verified=False,timeout_seconds=None,termination_policy='No elapsed-time kill; retain complete result or explicit tool error')
 start=time.monotonic()
 with (out/'route.log').open('w') as log:
  child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
  while child.poll() is None:
   try:child.wait(timeout=30)
   except subprocess.TimeoutExpired:pass
   print(round(time.monotonic()-start,1), '\n'.join((out/'route.log').read_text().splitlines()[-2:]),flush=True)
 result.update(exit=child.returncode,seconds=time.monotonic()-start)
 log=(out/'route.log').read_text();result['route_completed']='Routing complete.' in log
 result['errors']=[l for l in log.splitlines() if l.startswith('ERROR:') or 'Assertion failure' in l]
 if (out/'pnr.json').exists():
  report=json.loads((out/'pnr.json').read_text());result['fmax']=report.get('fmax');(out/'pnr.json.gz').write_bytes(gzip.compress((out/'pnr.json').read_bytes(),mtime=0));(out/'pnr.json').unlink()
 if (work/'routed.json').exists():
  result['routed_sha256']=digest((work/'routed.json').read_bytes())
  cells=next(iter(json.loads((work/'routed.json').read_text())['modules'].values()))['cells']
  result['physical_sites']=audit(cells)
  (out/'routed.json.gz').write_bytes(gzip.compress((work/'routed.json').read_bytes(),mtime=0))
 cache=binary.parent/'CMakeCache.txt'
 if cache.exists():(out/'CMakeCache.txt.gz').write_bytes(gzip.compress(cache.read_bytes(),mtime=0))
 result['compiler']=subprocess.check_output(['/usr/bin/g++','--version'],text=True).splitlines()[0]
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

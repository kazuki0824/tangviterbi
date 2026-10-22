"""Bounded full-fixture route with the previously verified compatible-pair packer."""
import collections,gzip,hashlib,json,os,subprocess,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ci.gowin_ff_site_audit import audit
D=ROOT/'reports/arbiter-parallel';W=ROOT.parent
binary=W/'nextpnr-build/nextpnr-himbaechel'
cmd=[str(binary),'--json',str(D/'folded.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt',f'cst={D}/pins.cst','--freq',str(1080/7),'--seed','1','--placer','heap','--placer-heap-cell-placement-timeout','1000000','--router','router1','--report',str(D/'pnr.json'),'--write',str(D/'routed.json')]
(D/'route-command.json').write_text(json.dumps(cmd,indent=2)+'\n')
r=dict(timeout_seconds=1800,binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),mapped_sha256=hashlib.sha256((D/'folded.json').read_bytes()).hexdigest(),target_MHz=1080/7,whole_receiver_verified=False)
r['backend_source_sha256']={f:hashlib.sha256((W/'nextpnr-source'/f).read_bytes()).hexdigest()for f in ['himbaechel/uarch/gowin/gowin.cc','himbaechel/uarch/gowin/pack_luts.cc']}
r['chipdb_sha256']=hashlib.sha256((W/'toolchain/oss-cad-suite/share/nextpnr/himbaechel/gowin/chipdb-GW2A-18C.bin').read_bytes()).hexdigest()
assert r['chipdb_sha256']=='28e74084da573c220ace2dd9ca381abf0f31db6be6599b81761dfc2416b4e8a3'
start=time.monotonic()
with (D/'route.log').open('w')as f:
 p=subprocess.Popen(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
 while p.poll() is None:
  try:p.wait(timeout=30)
  except subprocess.TimeoutExpired:pass
  lines=(D/'route.log').read_text().splitlines()
  print(f'{time.monotonic()-start:.1f}s '+(' | '.join(lines[-2:])),flush=True)
  if time.monotonic()-start>=1800 and p.poll() is None:p.kill();p.wait();r['timeout']=True
r.update(exit=p.returncode,seconds=time.monotonic()-start)
log=(D/'route.log').read_text();r['route_completed']='Routing complete.'in log;r['errors']=[x for x in log.splitlines()if x.startswith('ERROR:')]
if (D/'pnr.json').exists():
 t=json.loads((D/'pnr.json').read_text());r['fmax']=t.get('fmax')
 if r['route_completed']:
  c=next(iter(json.loads((D/'routed.json').read_text())['modules'].values()))['cells'];r['physical_sites']=audit(c)
  path=t['critical_paths'][0]['path'];s=collections.Counter()
  for arc in path:s[arc['type']]+=arc['delay']
  r.update(path_delay_ns_by_type=dict(s),launch=path[0]['from'],capture=path[-1]['to'],logic_stages=sum(x['type']=='logic'for x in path))
for n in ['pnr.json','routed.json']:
 pth=D/n
 if pth.exists():r[n+'_sha256']=hashlib.sha256(pth.read_bytes()).hexdigest();(D/(n+'.gz')).write_bytes(gzip.compress(pth.read_bytes(),mtime=0))
(D/'route-result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)

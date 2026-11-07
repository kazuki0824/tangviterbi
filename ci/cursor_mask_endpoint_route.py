"""Observe the frozen cursor-mask netlist with full failing-endpoint diagnostics."""
import collections,gzip,hashlib,json,os,subprocess,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ci.gowin_ff_site_audit import audit
seed=int(sys.argv[1]);assert seed in [1,2]
S=ROOT/'reports/controller-cursor-mask';D=ROOT/f'reports/cursor-mask-endpoints-seed{seed}';D.mkdir(exist_ok=True);W=ROOT.parent
binary=W/'nextpnr-build/nextpnr-himbaechel-endpoints'
cmd=[str(binary),'--json',str(S/'folded.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt',f'cst={S}/pins.cst','--freq',str(1080/7),'--seed',str(seed),'--placer','heap','--placer-heap-cell-placement-timeout','1000000','--router','router1','--report',str(D/'pnr.json'),'--write',str(D/'routed.json')]
(D/'route-command.json').write_text(json.dumps(cmd,indent=2)+'\n')
r=dict(timeout_seconds=None,termination_policy="No elapsed-time kill; record progress and decide explicitly on tool failure, resource trouble or justified priority change",binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),mapped_sha256=hashlib.sha256((S/'folded.json').read_bytes()).hexdigest(),target_MHz=1080/7,whole_receiver_verified=False,seed=seed,rtl_changed=False,reason='Seed 1 validates diagnostic equivalence; seed 2 tests alternative physical locality without changing arithmetic or cycle counts')
r['backend_source_sha256']={f:hashlib.sha256((W/'nextpnr-source'/f).read_bytes()).hexdigest()for f in ['himbaechel/uarch/gowin/gowin.cc','himbaechel/uarch/gowin/pack_luts.cc','common/kernel/timing.cc','common/route/router1.cc']}
r['chipdb_sha256']=hashlib.sha256((W/'toolchain/oss-cad-suite/share/nextpnr/himbaechel/gowin/chipdb-GW2A-18C.bin').read_bytes()).hexdigest()
assert r['chipdb_sha256']=='28e74084da573c220ace2dd9ca381abf0f31db6be6599b81761dfc2416b4e8a3'
assert r['mapped_sha256']=='42492e77e6565ac4ecf60144bc8f748a25e76976bbbf7c6c0820e38286c30f39'
start=time.monotonic()
with (D/'route.log').open('w')as f:
 p=subprocess.Popen(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
 while p.poll() is None:
  try:p.wait(timeout=30)
  except subprocess.TimeoutExpired:pass
  lines=(D/'route.log').read_text().splitlines()
  print(f'{time.monotonic()-start:.1f}s '+(' | '.join(lines[-2:])),flush=True)
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
for f,h in r['backend_source_sha256'].items():assert hashlib.sha256((W/'nextpnr-source'/f).read_bytes()).hexdigest()==h
(D/'route-result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)

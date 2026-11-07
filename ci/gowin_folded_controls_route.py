"""Measure the control-folded netlist under unchanged official backend rules."""
import collections,gzip,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ci.shared_sdf_evidence import run
from ci.gowin_ff_site_audit import audit
from ci.gowin_control_capacity_audit import audit as control_audit

def main():
 src=ROOT/'reports/shared-receiver-fft-tile-onehot-prebuffer-route';d=ROOT/'reports/shared-receiver-fft-tile-folded-controls-route';d.mkdir(exist_ok=True)
 assert run([sys.executable,str(ROOT/'ci/gowin_fold_identity_controls.py'),str(src/'mapped.json.gz'),str(d/'mapped.json')],ROOT,d/'transform.log',120)==0
 (d/'pins.cst').write_bytes((src/'pins.cst').read_bytes())
 binary=ROOT.parent/'toolchain/oss-cad-suite/bin/nextpnr-himbaechel'
 common=[str(binary),'--json',str(d/'mapped.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt',f'cst={d}/pins.cst']
 cmd=common+['--pack-only','--write',str(d/'packed.json')];(d/'pack-command.json').write_text(json.dumps(cmd,indent=2)+'\n');assert run(cmd,ROOT,d/'pack.log',120)==0
 cells=json.loads((d/'packed.json').read_text())['modules']['top']['cells'];gate=audit(cells)
 (d/'placement-gate.json').write_text(json.dumps(dict(full=gate,control=control_audit(cells)),indent=2)+'\n')
 cmd=common+['--freq',str(1080/7),'--seed','1','--placer','heap','--placer-heap-cell-placement-timeout','1000000','--report',str(d/'pnr.json'),'--write',str(d/'routed.json')]
 (d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 code=run(cmd,ROOT,d/'pnr.log',600)if gate['excess']<=0 else None
 log=(d/'pnr.log').read_text()if(d/'pnr.log').exists()else''
 result=dict(pnr_exit=code,route_completed='Routing complete.'in log,full_fixture_bound=gate,whole_receiver_verified=False,external_IO_STA_verified=False,errors=[x for x in log.splitlines()if x.startswith('ERROR:')],source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in ['ci/gowin_folded_controls_route.py','ci/gowin_fold_identity_controls.py','tests/test_gowin_fold_identity_controls.py']})
 if(d/'pnr.json').exists():result['pnr_report']=json.loads((d/'pnr.json').read_text())
 (d/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in ['source_sha256','pnr_report']}))
 for n in ['mapped.json','packed.json','routed.json']:
  p=d/n
  if p.exists():(d/(n+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0));p.unlink()
if __name__=='__main__':main()

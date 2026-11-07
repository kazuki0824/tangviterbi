"""Pre-materialize required FF identity LUTs; apply unchanged backend rules."""
import gzip,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ci.shared_sdf_evidence import run
from ci.gowin_ff_site_audit import audit
from ci.shared_receiver_fft_tile_compact_bram_probe_evidence import FILES

def main():
 src=ROOT/'reports/shared-receiver-fft-tile-compact-bram-probe-pack';d=ROOT/'reports/shared-receiver-fft-tile-compact-bram-probe-prebuffer-sa-route';d.mkdir(exist_ok=True)
 assert run([sys.executable,str(ROOT/'ci/gowin_materialize_ff_inputs.py'),str(src/'mapped.json.gz'),str(d/'mapped.json')],ROOT,d/'transform.log',60)==0
 (d/'pins.cst').write_bytes((src/'pins.cst').read_bytes())
 common=['nextpnr-himbaechel','--json',str(d/'mapped.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt',f'cst={d}/pins.cst']
 pack=common+['--pack-only','--write',str(d/'packed.json')];(d/'pack-command.json').write_text(json.dumps(pack,indent=2)+'\n')
 assert run(pack,ROOT,d/'pack.log',120)==0
 full=audit(json.loads((d/'packed.json').read_text())['modules']['top']['cells'])
 (d/'placement-gate.json').write_text(json.dumps(full,indent=2)+'\n')
 cmd=common+['--freq',str(1080/7),'--seed','1','--placer','sa','--report',str(d/'pnr.json'),'--write',str(d/'routed.json')]
 (d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 code=run(cmd,ROOT,d/'pnr.log',300)if full['excess']<=0 else None
 log=(d/'pnr.log').read_text()if(d/'pnr.log').exists()else''
 result=dict(full_fixture_bound=full,pnr_exit=code,route_completed='Routing complete.'in log,whole_receiver_verified=False,external_IO_STA_verified=False,source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in FILES+['ci/gowin_materialize_ff_inputs.py','ci/compact_bram_probe_prebuffer_sa_route.py']},errors=[x for x in log.splitlines()if x.startswith('ERROR:')])
 if(d/'pnr.json').exists():result['pnr_report']=json.loads((d/'pnr.json').read_text())
 (d/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in ['source_sha256','pnr_report']}))
 for n in ['mapped.json','packed.json','routed.json']:
  q=d/n
  if q.exists():(d/(n+'.gz')).write_bytes(gzip.compress(q.read_bytes(),mtime=0));q.unlink()
if __name__=='__main__':main()

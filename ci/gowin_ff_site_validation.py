"""Validate the fixed-netlist bound against two already routed designs."""
import gzip,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ci.gowin_ff_site_audit import audit,read,scope_cells
from ci.shared_sdf_evidence import run

def main():
 out=ROOT/'reports/ff-site-validation';out.mkdir(exist_ok=True)
 result={}
 for source in ('t-time-tile-dma-direct-route','shared-receiver-fft-metadata-refresh-evidence'):
  old=ROOT/'reports'/source;p=out/source;p.mkdir(exist_ok=True)
  (p/'mapped.json.gz').write_bytes((old/'mapped.json.gz').read_bytes())
  (p/'mapped.json').write_bytes(gzip.decompress((p/'mapped.json.gz').read_bytes()))
  (p/'pins.cst').write_bytes((old/'pins.cst').read_bytes())
  cmd=['nextpnr-himbaechel','--json',str(p/'mapped.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt',f'cst={p}/pins.cst','--pack-only','--write',str(p/'packed.json')]
  (p/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
  assert run(cmd,ROOT,p/'pack.log',120)==0
  (p/'packed.json.gz').write_bytes(gzip.compress((p/'packed.json').read_bytes(),mtime=0))
  full,core,regs=scope_cells(p)
  r=read(old/'routed.json.gz')['modules']['top']['cells']
  h={n for n in r if n in regs or n.startswith('digest')or n.removesuffix('_passthrough_lut$')in regs}
  actual={n:c for n,c in r.items()if n not in h}
  bound=audit(core);routed=audit(actual)
  assert bound['optimistic_logic_site_lower_bound']<=routed['packed_logic_with_ram_blockers']
  recorded=read(old/'summary.json')['logic_with_ram_blockers']
  assert routed['packed_logic_with_ram_blockers']==recorded
  result[source]=dict(bound=bound,routed_logic=recorded,actual_added_passthrough=sum(n.endswith('_passthrough_lut$')for n in actual),unmatched_after_route=routed['minimum_extra_passthrough_LUTs'],harness_registers=len(regs),source_sha256={n:hashlib.sha256((old/n).read_bytes()).hexdigest()for n in ('mapped.json.gz','routed.json.gz','summary.json')})
  (p/'mapped.json').unlink();(p/'packed.json').unlink()
 result['auditor_sha256']=hashlib.sha256((ROOT/'ci/gowin_ff_site_audit.py').read_bytes()).hexdigest()
 result['generator_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

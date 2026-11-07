"""Route the complete DSP-backed fixture; do not subtract a name-prefix core.
All cells count toward the placement gate. Source-attributed probe registers
are separated only for conservative reporting; XOR logic stays included.
"""
import argparse,collections,gzip,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ci.shared_sdf_evidence import run
from ci.gowin_ff_site_audit import audit,read
from ci.shared_receiver_fft_tile_compact_dsp_probe_evidence import FILES

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();src=a.input.resolve();d=a.output.resolve();d.mkdir(parents=True,exist_ok=True)
 def load(n):return read(src/n if(src/n).exists()else src/(n+'.gz'))
 m=load('mapped.json');packed=load('packed.json')['modules']['top']['cells'];cells=m['modules']['shared_receiver_fft_tile_probe']['cells']
 regs={n for n,c in cells.items()if c['type'].startswith('DFF')and FILES[-1]in c.get('attributes',{}).get('src','').split('|')[0]}
 dsp={n for n,c in cells.items()if c['type']=='ALU54D'and n.startswith('scan_dsp[')}
 full=audit(packed);core=audit({n:c for n,c in packed.items()if n not in regs})
 assert len(regs)==176 and len(dsp)==21,(len(regs),len(dsp))
 assert core['FF']==8483,core
 assert sum(c['type']=='MULT18X18'for c in packed.values())==6
 gate=dict(full=full,core_plus_probe_logic=core,probe_registers=176,probe_ALU54D=21,probe_MULT18_equivalent=42,core_MULT18X18=6,
  scope='Full fixture gate. Conservative core report retains all LUT logic including checksum; no digest-name stripping.',passed_necessary_condition=full['excess']<=0)
 (d/'placement-gate.json').write_text(json.dumps(gate,indent=2)+'\n')
 for n in ['mapped.json','packed.json','core-mapped.json']:
  data=json.dumps(load(n)).encode();(d/(n+'.gz')).write_bytes(gzip.compress(data,mtime=0))
 assert full['excess']<=0,full
 (d/'mapped.json').write_text(json.dumps(m));(d/'pins.cst').write_bytes((src/'pins.cst').read_bytes())
 cmd=['nextpnr-himbaechel','--json',str(d/'mapped.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt',f'cst={d}/pins.cst','--freq',str(1080/7),'--seed','1','--placer','sa','--report',str(d/'pnr.json'),'--write',str(d/'routed.json')]
 (d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n');code=run(cmd,ROOT,d/'pnr.log',300)
 log=(d/'pnr.log').read_text();result=dict(pnr_exit=code,route_completed='Routing complete.'in log,whole_receiver_verified=False,external_IO_STA_verified=False,source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in FILES+['ci/compact_dsp_probe_sa_route.py']},errors=[x for x in log.splitlines()if x.startswith('ERROR:')])
 if(d/'pnr.json').exists():result['pnr_report']=json.loads((d/'pnr.json').read_text())
 (d/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in ['source_sha256','pnr_report']}))
 for n in ['mapped.json','routed.json']:
  q=d/n
  if q.exists():(d/(n+'.gz')).write_bytes(gzip.compress(q.read_bytes(),mtime=0));q.unlink()
if __name__=='__main__':main()

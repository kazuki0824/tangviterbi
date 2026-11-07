"""Shared T3+TC8 context core comparison; no FIFO, scheduler, metric generator or receiver."""
import argparse,gzip,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'experiments'))
from shared_tc8_k7_context import generate
from ci.shared_sdf_evidence import run
from ci.t_soft_reader_evidence import count,logic,ff
FILES=['rtl/shared_k7_context.sv','experiments/shared_tc8_k7_context.sv','experiments/shared_tc8_k7_boundary.sv','experiments/shared_tc8_k7_probe.sv']
PROVENANCE=FILES+['experiments/shared_tc8_k7_context.py','ci/shared_tc8_k7_evidence.py','ci/t_soft_reader_evidence.py']
def measure(d,extended):
 d.mkdir(parents=True,exist_ok=True);generated=generate();assert generated==(ROOT/'experiments/shared_tc8_k7_context.sv').read_text()

 for prefix,top,files in [('core-','shared_tc8_k7_boundary',FILES[:-1]),('','shared_tc8_k7_probe',FILES)]:
  (d/(prefix+'synth.ys')).write_text('read_verilog -sv '+' '.join(str(ROOT/f)for f in files)+f'\nchparam -set USE_TC8 {extended} {top}\nsynth_gowin -family gw2a -top {top} -nowidelut -json {d}/{prefix}mapped.json\ncheck -assert\n')
  assert run(['yosys','-Q','-s',str(d/(prefix+'synth.ys'))],ROOT,d/(prefix+'synth.log'),600)==0
 pins=[('clk',4),('resetn',87),('scan_enable',73),('scan_in',74),('signature',75)]
 (d/'pins.cst').write_text(''.join(f'IO_LOC "{s}" {n};\nIO_PORT "{s}" IO_TYPE=LVCMOS33;\n'for s,n in pins))
 cmd=['nextpnr-himbaechel','--json',str(d/'mapped.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt',f'cst={d}/pins.cst','--freq',str(1080/7),'--seed','1','--report',str(d/'pnr.json'),'--write',str(d/'routed.json')]
 (d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n');code=run(cmd,ROOT,d/'pnr.log',600)
 mapped=json.loads((d/'mapped.json').read_text())['modules']['shared_tc8_k7_probe']['cells']
 regs={k for k,v in mapped.items() if v['type'].startswith('DFF') and FILES[-1] in v.get('attributes',{}).get('src','')}
 assert 28<=len(regs)<=72,len(regs)
 result=dict(scope=__doc__,TC8_extension=bool(extended),metric_width=13,clocks_per_step=2,target_MHz=1080/7,pnr_exit=code,harness_FF=len(regs),
 source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in PROVENANCE},generated_sha256=hashlib.sha256(generated.encode()).hexdigest(),whole_receiver_verified=False,external_IO_STA_verified=False,output_backpressure_supported=False)
 result['core_mapped_cells']=count(json.loads((d/'core-mapped.json').read_text())['modules']['shared_tc8_k7_boundary']['cells'])
 if (d/'routed.json').exists():
  routed=json.loads((d/'routed.json').read_text())['modules']['top']['cells']
  harness={k:v for k,v in routed.items() if k in regs or k.startswith('digest') or k.removesuffix('_passthrough_lut$') in regs}
  actual={k:v for k,v in routed.items() if k not in harness};hc,ac,tc=count(harness),count(actual),count(routed)
  report=json.loads((d/'pnr.json').read_text());u=report['utilization'];assert logic(tc)==u['LUT4']['used']+u['ALU']['used'];assert ff(hc)==len(regs);assert ff(tc)==u['DFF']['used']
  ram=ac.get('RAM16SDP4',0)
  result.update(core_cells=ac,harness_cells=hc,logic_with_ram_blockers=logic(ac)+4*ram,FF_sites_with_ram_blockers=ff(ac)+6*ram,BSRAM=u['BSRAM']['used'],DSP18=u['MULT18X18']['used'],RAM16SDP4=ram,fmax=report['fmax'],utilization=u)
 log=(d/'pnr.log').read_text();result['route_completed']='Routing complete.'in log;result['errors']=[x for x in log.splitlines()if x.startswith('ERROR:')]
 result['partial_target_pass']=code==0 and result['route_completed'] and not result['errors']
 result['yosys_version']=subprocess.check_output(['yosys','-V'],text=True).strip();result['pnr_version']=subprocess.check_output(['nextpnr-himbaechel','--version'],stderr=subprocess.STDOUT,text=True).strip()
 (d/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items()if not k.endswith('cells') and k not in ('utilization','source_sha256')},indent=2),flush=True)
 for name in ('mapped.json','core-mapped.json','routed.json','synth.log','core-synth.log'):
  p=d/name
  if p.exists():Path(str(p)+'.gz').write_bytes(gzip.compress(p.read_bytes(),mtime=0));p.unlink()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 for extended in (0,1):measure(a.output.resolve()/('extended'if extended else'baseline'),extended)
if __name__=='__main__':main()

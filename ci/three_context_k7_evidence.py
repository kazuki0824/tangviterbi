"""Three-context 16-ACS K7 partial CAD probe; no receiver or external I/O qualification."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ci.shared_sdf_evidence import run
from experiments.three_context_k7 import generate

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--dual-read',action='store_true');p.add_argument('--frequency',type=float,default=108);a=p.parse_args()
 d=a.output.resolve();d.mkdir(parents=True,exist_ok=True)
 for name in ('mapped.json','pnr.json','summary.json'):(d/name).unlink(missing_ok=True)
 rtl=generate(not a.dual_read);(d/'dut.sv').write_text(rtl)
 inputs=['resetn','slot_valid','slot_context[0]','slot_context[1]','in_valid']+[f'soft0[{i}]'for i in range(8)]+[f'soft1[{i}]'for i in range(8)]+['erasure[0]','erasure[1]']
 pins=[35,25,26,27,28,29,30,33,34,40,36,41,42,51,53,54,55,56,57,37,38,31,32]
 outputs=['slot_ready','out_context[0]','out_context[1]','in_ready','out_valid','out_bit']
 assert len(inputs)==len(pins)
 locations=[('clk',52,'LVCMOS33')]+[(s,n,'LVCMOS33')for s,n in zip(inputs,pins)]+[(s,n,'LVCMOS18')for s,n in zip(outputs,[10,11,13,14,15,16])]
 (d/'pins.cst').write_text(''.join(f'IO_LOC "{s}" {n};\nIO_PORT "{s}" IO_TYPE={v};\n'for s,n,v in locations))
 (d/'synth.ys').write_text(f'read_verilog -sv {d}/dut.sv\nsynth_gowin -family gw1n -top three_context_k7 -nowidelut -json {d}/mapped.json\ncheck -assert\n')
 result=dict(scope=__doc__,contexts=3,split_banks=not a.dual_read,clocks_per_slot=4,target_MHz=a.frequency,
             generated_sha256=hashlib.sha256(rtl.encode()).hexdigest(),
             source_sha256={x:hashlib.sha256((ROOT/x).read_bytes()).hexdigest()for x in ['experiments/three_context_k7.py','rtl/shared_k7_context.sv']},
             external_IO_STA_verified=False,whole_receiver_verified=False,
             input_scheduler_and_FIFO_included=False,output_backpressure_supported=False,
             pin_scope='fixed probe inputs and six LED outputs; not receiver wiring or external STA',
             yosys_version=subprocess.check_output(['yosys','-V'],text=True).strip())
 result['synth_exit']=run(['yosys','-Q','-s',str(d/'synth.ys')],ROOT,d/'synth.log',600)
 if result['synth_exit']==0:
  cmd=['nextpnr-himbaechel','--json',str(d/'mapped.json'),'--device','GW1NR-LV9QN88PC6/I5','--vopt','family=GW1N-9C','--vopt',f'cst={d}/pins.cst','--freq',str(a.frequency),'--seed','1','--report',str(d/'pnr.json')]
  (d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
  result['pnr_exit']=run(cmd,ROOT,d/'pnr.log',600)
  result['pnr_version']=subprocess.check_output(['nextpnr-himbaechel','--version'],stderr=subprocess.STDOUT,text=True).strip()
  log=(d/'pnr.log').read_text();result['route_completed']='Routing complete.'in log
  result['errors']=[x for x in log.splitlines()if x.startswith('ERROR:')]
  if (d/'pnr.json').exists():
   report=json.loads((d/'pnr.json').read_text());u=report['utilization'];result['utilization']=u;result['fmax']=report['fmax']
   result['logic_positions']=sum(u.get(k,{}).get('used',0)for k in ('LUT4','ALU'))
   result['FF']=u.get('DFF',{}).get('used',0);result['BSRAM']=u.get('BSRAM',{}).get('used',0)
   ram=u.get('RAM16SDP4',{}).get('used',0)
   result['RAM16SDP4']=ram
   result['ram_blocker_accounting']='9K packing/log must be inspected; do not apply GW2A rule automatically'
  result['partial_target_pass']=result['pnr_exit']==0 and result['route_completed'] and not result['errors']
 (d/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

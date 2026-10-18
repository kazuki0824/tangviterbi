"""Four-context K7 plus input queues and scheduler; partial CAD probe."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ci.shared_sdf_evidence import run
from experiments.shared_k7_context import generate

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--frequency',type=float,default=1080/7);a=p.parse_args()
 d=a.output.resolve();d.mkdir(parents=True,exist_ok=True)
 for name in ('mapped.json','pnr.json','summary.json'):(d/name).unlink(missing_ok=True)
 rtl=(ROOT/'rtl/shared_k7_context.sv').read_text()+'\n'+(ROOT/'rtl/shared_k7_stream.sv').read_text();(d/'dut.sv').write_text(rtl)
 signals=['resetn','in_valid','in_ready','in_context[0]','in_context[1]','out_context[0]','out_context[1]']+[f'soft0[{i}]'for i in range(8)]+[f'soft1[{i}]'for i in range(8)]+['erasure[0]','erasure[1]','out_valid','out_bit']
 pins=[73,74,75,85,77,15,16,27,28,25,26,29,30,31,17,20,19,18,76,80,42,41,56,54,51,48,55]
 assert len(signals)==len(pins)
 (d/'pins.cst').write_text(''.join(f'IO_LOC "{s}" {n};\nIO_PORT "{s}" IO_TYPE=LVCMOS33;\n'for s,n in [('clk',4),*zip(signals,pins)]))
 (d/'synth.ys').write_text(f'read_verilog -sv {d}/dut.sv\nsynth_gowin -family gw2a -top shared_k7_stream -nowidelut -json {d}/mapped.json\ncheck -assert\n')
 result=dict(scope=__doc__,contexts=4,FIFO_words_per_context=16,maintenance_period_slots=128,clocks_per_slot=2,target_MHz=a.frequency,
             generated_sha256=hashlib.sha256(rtl.encode()).hexdigest(),
             source_sha256={x:hashlib.sha256((ROOT/x).read_bytes()).hexdigest()for x in ['rtl/shared_k7_context.sv','rtl/shared_k7_stream.sv','ci/shared_k7_stream_evidence.py']},
             external_IO_STA_verified=False,whole_receiver_verified=False,
             input_scheduler_and_FIFO_included=True,output_backpressure_supported=False,
             pin_scope='fixed test ports on J5/J6; not receiver wiring or board load timing',
             yosys_version=subprocess.check_output(['yosys','-V'],text=True).strip())
 result['synth_exit']=run(['yosys','-Q','-s',str(d/'synth.ys')],ROOT,d/'synth.log',600)
 if result['synth_exit']==0:
  cmd=['nextpnr-himbaechel','--json',str(d/'mapped.json'),'--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt',f'cst={d}/pins.cst','--freq',str(a.frequency),'--seed','1','--report',str(d/'pnr.json')]
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
   result['logic_sites_with_ram_blockers']=result['logic_positions']+4*ram
   result['FF_sites_with_ram_blockers']=result['FF']+6*ram
  result['partial_target_pass']=result['pnr_exit']==0 and result['route_completed'] and not result['errors']
 (d/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

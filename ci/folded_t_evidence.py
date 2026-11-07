#!/usr/bin/env python3
"""Reproducible like-for-like T decoder probes, not receiver qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experiments.folded_t_viterbi import generate
from experiments.s3_viterbi_traceback import generate as baseline
from ci.shared_sdf_evidence import run

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--lanes',type=int,choices=(0,16,22,32),required=True,help='0 is the verified existing 32-ACS baseline')
 p.add_argument('--pipeline',action='store_true')
 p.add_argument('--compact-survivor',action='store_true')
 p.add_argument('--onehot',action='store_true')
 p.add_argument('--erasures',action='store_true')
 p.add_argument('--registered-costs',action='store_true')
 p.add_argument('--shift-output',action='store_true')
 p.add_argument('--board',choices=('9k','20k'),required=True)
 p.add_argument('--frequency',type=float,required=True)
 p.add_argument('--output',type=Path,required=True)
 a=p.parse_args()
 if not a.lanes and any((a.pipeline,a.compact_survivor,a.onehot,a.registered_costs,a.shift_output)):
  p.error('baseline accepts --erasures only; folding options require nonzero --lanes')
 d=a.output.resolve();d.mkdir(parents=True,exist_ok=True)
 for f in ('mapped.json','pnr.json','summary.json'): (d/f).unlink(missing_ok=True)
 rtl=generate(a.lanes,a.pipeline,a.compact_survivor,a.onehot,a.erasures,a.registered_costs,a.shift_output) if a.lanes else baseline('modulo13-pipe').replace('module s3_viterbi_traceback','module folded_t_viterbi')
 if not a.lanes and a.erasures:
  sys.path.insert(0,str(ROOT/'experiments'))
  from s3_viterbi_erasure import source
  rtl=source().replace('module s3_viterbi_erasure','module folded_t_viterbi')
 (d/'dut.sv').write_text(rtl)
 # External soft pairs keep every input bit alive; no LFSR cost is subtracted.
 # Identical harness and pin order for baseline and folded variants.
 (d/'top.sv').write_text('''module folded_probe(input clk,resetn,valid,input[7:0] soft0,soft1,
 output ready,ov,ob);
 folded_t_viterbi dut(clk,resetn,valid,ready,soft0,soft1,ov,ob);
 endmodule\n''')
 if a.erasures:
  top=(d/'top.sv').read_text().replace('output ready,ov,ob);','input[1:0] erasure, output ready,ov,ob);').replace('soft0,soft1,ov,ob);','soft0,soft1,erasure,ov,ob);')
  (d/'top.sv').write_text(top)
 family='gw1n' if a.board=='9k' else 'gw2a'
 script=f'read_verilog -sv {d}/dut.sv {d}/top.sv\nsynth_gowin -family {family} -top folded_probe -nowidelut -json {d}/mapped.json\ncheck -assert\n'
 (d/'synth.ys').write_text(script)
 synth_rc=run(['yosys','-Q','-s',str(d/'synth.ys')],ROOT,d/'synth.log',600)
 result=dict(board=a.board,lanes=a.lanes or 32,baseline=a.lanes==0,pipeline=a.pipeline,compact_survivor=a.compact_survivor,onehot=a.onehot,erasures=a.erasures,registered_costs=a.registered_costs,shift_output=a.shift_output,
  scope='one T convolutional context with full block traceback; no receiver, depuncture, hierarchy/PHY',
  synth_exit=synth_rc,target_MHz=a.frequency,
  cycles_per_step=(64+(a.lanes or 32)-1)//(a.lanes or 32)+int(a.pipeline)+int(a.registered_costs),
  yosys_version=subprocess.check_output(['yosys','-V'],text=True).strip(),
  source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
   (ROOT/'experiments/folded_t_viterbi.py',ROOT/'experiments/s3_viterbi_traceback.py',ROOT/'rtl/viterbi_k7_32acs.sv',Path(__file__).resolve())},
  generated_rtl_sha256=hashlib.sha256(rtl.encode()).hexdigest(),
  receiver_adopted=False,external_io_STA_verified=False,complete_STA_verified=False)
 if synth_rc==0:
  device,fam,clock=('GW1NR-LV9QN88PC6/I5','GW1N-9C',52) if a.board=='9k' else ('GW2AR-LV18QN88C8/I7','GW2A-18C',4)
  pins=([35,25,26,27,28,29,30,33,34,40,36,41,42,51,53,54,55,56,57,37,38] if a.board=='9k' else [73,74,75,85,77,15,16,27,28,25,26,29,30,31,17,20,19,18,76,80,42])
  signals=['resetn','valid']+[f'soft0[{i}]' for i in range(8)]+[f'soft1[{i}]' for i in range(8)]+['ready','ov','ob']
  if a.erasures:
   pins += [31,32] if a.board=='9k' else [41,56]
   signals += ['erasure[0]','erasure[1]']
  (d/'pins.cst').write_text(''.join(f'IO_LOC "{s}" {n};\nIO_PORT "{s}" IO_TYPE=LVCMOS33;\n' for s,n in [('clk',clock),*zip(signals,pins)]))
  cmd=['nextpnr-himbaechel','--json',str(d/'mapped.json'),'--device',device,'--vopt',f'family={fam}','--vopt',f'cst={d}/pins.cst','--freq',str(a.frequency),'--seed','1','--report',str(d/'pnr.json')]
  (d/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
  result['pnr_exit']=run(cmd,ROOT,d/'pnr.log',600)
  result['pnr_version']=subprocess.check_output(['nextpnr-himbaechel','--version'],stderr=subprocess.STDOUT,text=True).strip()
  log=(d/'pnr.log').read_text();result['route_completed']='Routing complete.' in log
  result['errors']=[l for l in log.splitlines() if l.startswith('ERROR:')]
  result['timing_limitations']=[l for l in log.splitlines() if 'timing' in l.lower() and any(w in l.lower() for w in ('no ','missing','unknown','unmodel'))]
  if (d/'pnr.json').exists():
   rpt=json.loads((d/'pnr.json').read_text());use=rpt['utilization'];result['utilization']=use;result['fmax']=rpt['fmax']
   result['logic_positions']=sum(use.get(k,{}).get('used',0) for k in ('LUT4','ALU'))
   result['FF']=use.get('DFF',{}).get('used',0)
   result['BSRAM']=use.get('BSRAM',{}).get('used',0)
  result['partial_target_pass']=result['pnr_exit']==0 and result['route_completed'] and not result['errors']
 (d/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 return synth_rc
if __name__=='__main__':raise SystemExit(main())

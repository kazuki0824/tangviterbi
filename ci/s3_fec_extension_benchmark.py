#!/usr/bin/env python3
from pathlib import Path
import sys,subprocess,json,hashlib,argparse
r=Path(__file__).resolve().parents[1];sys.path.insert(0,str(r/'experiments'));sys.path.insert(0,str(r/'ci'))
from s3_tc8psk import source
from s3_viterbi_erasure import source as erasure
from s3_rs_isdb import source as rs
from s3_area_benchmark import synth,run
out=r/'build/s3-fec-extensions';out.mkdir(exist_ok=True)
(out/'rs.sv').write_text(rs(True))
parser=argparse.ArgumentParser()
parser.add_argument('--kind',choices=['tc8psk','erasure','tc8psk-metric'],action='append')
parser.add_argument('--seeds',type=int,nargs='+',default=[1,2,3])
a=parser.parse_args()
results={}
for kind,gen in [('tc8psk',source),('erasure',erasure),('tc8psk-metric',source)]:
 if a.kind and kind not in a.kind:continue
 tc=kind.startswith('tc8psk')
 d=out/kind;d.mkdir(exist_ok=True);s=gen();top='s3_'+('tc8psk' if tc else 'viterbi_erasure');p=d/'viterbi.sv';p.write_text(s)
 counts=synth([p],top,d/'module',narrow=True)
 results[kind]={'module':counts,'rtl_sha256':hashlib.sha256(s.encode()).hexdigest()}
 (d/'module-result.json').write_text(json.dumps(results[kind],indent=2)+'\n')
 print(kind,counts,flush=True)
 bench=(r/'rtl/benchmark_top.sv').read_text()
 bench=bench.replace('viterbi_k7_32acs u_viterbi',top+' u_viterbi')
 if tc:
  bench=bench.replace('reg [31:0] lfsr;','reg [63:0] lfsr;')
  bench=bench.replace("lfsr <= 32'h1ace_b00c;","lfsr <= 64'hc14fb4391aceb00c;")
  bench=bench.replace('{lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]}','{lfsr[62:0], lfsr[63] ^ lfsr[62] ^ lfsr[60] ^ lfsr[59]}')
  bench=bench.replace('wire vit_bit;','wire [1:0] tc_bits;\n    wire vit_bit=^tc_bits;')
  bench=bench.replace('.soft0(lfsr[7:0]),\n                    .soft1(lfsr[15:8]),','.costs(lfsr[35:0]),\n                    .b1_choice(lfsr[39:36]),',1)
  bench=bench.replace('.out_bit(vit_bit)','.out_bits(tc_bits)',1)
 else:
  bench=bench.replace('.soft0(lfsr[7:0]),','.erasure(lfsr[17:16]),\n                    .soft0(lfsr[7:0]),',1)
 extra=[]
 if kind=='tc8psk-metric':
  extra=[r/'rtl/s3_tc8psk_metric.sv']
  results[kind]['metric_module']=synth(extra,'s3_tc8psk_metric',d/'metric-module',narrow=True)
  results[kind]['metric_rtl_sha256']=hashlib.sha256(extra[0].read_bytes()).hexdigest()
  bench=bench.replace('    wire vit_ready;', "    wire vit_ready,mv; wire [35:0] mc; wire [3:0] mb;\n    s3_tc8psk_metric metric(clk,resetn,1'b1,,lfsr[15:0],lfsr[31:16],mv,vit_ready,mc,mb);")
  bench=bench.replace('.in_valid(vit_ready)', '.in_valid(mv)',1).replace('.costs(lfsr[35:0])','.costs(mc)',1).replace('.b1_choice(lfsr[39:36])','.b1_choice(mb)',1)
 bp=d/'benchmark_top.sv';bp.write_text(bench)
 routed=d/'fec-mem';routed.mkdir(exist_ok=True)
 results[kind]['FEC_mem_synthesis']=synth([r/'rtl/viterbi_k7_16acs.sv',p,out/'rs.sv',r/'rtl/psram_ctrl.sv',bp]+extra, 'benchmark_top',routed,mem=1,narrow=True)
 trials=[]
 for seed in a.seeds:
  suffix='' if seed==1 else '-seed'+str(seed)
  rp=routed/('report'+suffix+'.json')
  rc=run(['nextpnr-himbaechel','--json',str(routed/'design.json'),'--device','GW1NR-LV9QN88PC6/I5','--vopt','family=GW1N-9C','--vopt','cst=constraints/tangnano9k.cst','--freq','99','--seed',str(seed),'--report',str(rp)],routed/('pnr'+suffix+'.log'))
  report=json.loads(rp.read_text()) if rp.exists() else {}
  trial=dict(seed=seed,exit_code=rc,fmax=report.get('fmax'),utilization=report.get('utilization'))
  trials.append(trial)
  if rc==0:break
 results[kind]['pnr_trials']=trials
 results[kind]['pnr']=trials[-1]


report=dict(scope='Partial FEC+protocol controller sizing. tc8psk-metric includes the symbol metric unit. No synchronization, TMCC, deinterleavers, communication or physical PSRAM.',results=results,receiver_adopted=False)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
target=r/'reports/s3-fec-extensions.json'
if a.kind and target.exists():
 previous=json.loads(target.read_text())['results'];previous.update(results);report['results']=previous
target.write_text(json.dumps(report,indent=2)+'\n')

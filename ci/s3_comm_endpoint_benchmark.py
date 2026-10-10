#!/usr/bin/env python3
"""Physical-pin partial endpoint benchmark; never a receiver-fit certificate."""
from pathlib import Path
import hashlib
import json
import subprocess
import shutil
import argparse

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seeds',type=int,nargs='+',default=[1,2,3])
args=parser.parse_args()
out=ROOT/'build/s3-comm-endpoint';out.mkdir(parents=True,exist_ok=True)
# Keep every measured revision, including failures, before replacing outputs.
if (out/'result.json').exists():
 old=json.loads((out/'result.json').read_text())
 trial=out/'trials'/hashlib.sha256(json.dumps(old['sources'],sort_keys=True).encode()).hexdigest()[:12]
 trial.mkdir(parents=True,exist_ok=True)
 for name in ('result.json','pnr.log','synth.log','report.json','stat.json','clocks.py'):
  if (out/name).exists():shutil.copy2(out/name,trial/name)
sources=['rtl/s3_async_fifo.sv','rtl/s3_spi_rx.sv','rtl/s3_page_guard.sv',
         'rtl/s3_page_reorder.sv','rtl/s3_rx_page_store.sv','rtl/s3_spi_iq_tx.sv',
         'experiments/s3_comm_endpoint_benchmark.sv']
(out/'synth.ys').write_text('read_verilog -sv '+' '.join(sources)+'\n'+
 'synth_gowin -top s3_comm_endpoint_benchmark -family gw1n -nowidelut -json '+str(out/'design.json')+'\n'+
 'tee -o '+str(out/'stat.json')+' stat -json\ncheck -assert\n')
with (out/'synth.log').open('w') as f:
 subprocess.run(['yosys','-Q','-T','-s',str(out/'synth.ys')],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
netlist=json.loads((out/'design.json').read_text())['modules']['s3_comm_endpoint_benchmark']
clocks=[]
for port,freq in [('clk',99),('spi2_sclk',80),('spi3_sclk',80)]:
 pad=netlist['ports'][port]['bits']
 buffers=[c for c in netlist['cells'].values() if c['type']=='IBUF' and c['connections']['I']==pad]
 if len(buffers)!=1:raise ValueError('ambiguous IBUF for '+port)
 bits=buffers[0]['connections']['O']
 globals_=[c for c in netlist['cells'].values() if c['type']=='BUFG' and c['connections']['I']==bits]
 if globals_:bits=globals_[0]['connections']['O']
 aliases=[n for n,v in netlist['netnames'].items() if v['bits']==bits and not n.startswith('$')]
 if not aliases:raise ValueError('missing clock net alias')
 clocks.append((min(aliases,key=len),freq))
(out/'clocks.py').write_text(''.join(f'ctx.addClock({name!r},{freq})\n' for name,freq in clocks))
trials=[]
for seed in args.seeds:
 log=out/f'pnr-seed{seed}.log';rp=out/f'report-seed{seed}.json'
 with log.open('w') as f:
  rc=subprocess.run(['nextpnr-himbaechel','--json',str(out/'design.json'),'--device','GW1NR-LV9QN88PC6/I5',
   '--vopt','family=GW1N-9C','--vopt','cst=experiments/s3_spi_rx_benchmark.cst',
   '--freq','99','--pre-pack',str(out/'clocks.py'),'--seed',str(seed),'--report',str(rp)],
   cwd=ROOT,stdout=f,stderr=subprocess.STDOUT).returncode
 r=json.loads(rp.read_text()) if rp.exists() else {}
 warnings=[line for line in log.read_text().splitlines() if line.startswith('Warning:')]
 trials.append(dict(seed=seed,exit_code=rc,fmax=r.get('fmax'),warnings=warnings))
 shutil.copy2(log,out/'pnr.log')
 if rp.exists():shutil.copy2(rp,out/'report.json')
 if rc==0:break
report=dict(scope=__doc__,exit_code=rc,clock_nets=clocks,fmax=r.get('fmax'),utilization=r.get('utilization'),warnings=warnings,
 pnr_trials=trials,physical_timing_proven=False,
 sources={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
 synthesis=json.loads((out/'stat.json').read_text()),
 absent=['physical PSRAM','payload-memory reads','RF demodulation','core PLL','external IO delay/skew constraints','S3 status firmware'],
 receiver_adopted=False)
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
(ROOT/'reports/s3-comm-endpoint.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('exit_code','clock_nets','fmax')},indent=2))

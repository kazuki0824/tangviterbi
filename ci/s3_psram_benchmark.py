#!/usr/bin/env python3
"""Physical-pin PSRAM BIST synthesis, P&R and evidence (not receiver fit)."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--seeds',type=int,nargs='+',default=[1,2,3])
p.add_argument('--bridge',action='store_true',help='Include SPI, page store and reader')
p.add_argument('--fec',action='store_true',help='Co-place independent S metric/TC8PSK/RS workload, not a receiver')
p.add_argument('--pnr-timeout',type=int,default=180,help='Wall seconds per placement seed; timeout is NOT a fit proof')
p.add_argument('--placer',choices=('heap','sa'),default='heap')
p.add_argument('--heap-cell-timeout',type=int,default=8,help='nextpnr cell-placement divisor; larger bounds each search sooner')
args=p.parse_args()
if args.fec:args.bridge=True
name='s3-memory-fec' if args.fec else 's3-memory-bridge' if args.bridge else 's3-psram'
top='s3_memory_fec_benchmark' if args.fec else 's3_memory_bridge_benchmark' if args.bridge else 's3_psram_benchmark'
out=ROOT/f'build/{name}-pnr';out.mkdir(parents=True,exist_ok=True)
sources=['rtl/s3_psram_burst.sv','rtl/s3_psram_queue.sv','rtl/s3_psram_phy.sv',
         'rtl/s3_psram_clock.sv','experiments/s3_psram_benchmark.sv']
if args.bridge:
    sources=sources[:-1]+['rtl/s3_async_fifo.sv','rtl/s3_spi_rx.sv','rtl/s3_page_guard.sv',
        'rtl/s3_page_reorder.sv','rtl/s3_rx_page_store.sv','rtl/s3_psram_page_reader.sv',
        'rtl/s3_spi_memory_bridge.sv','experiments/s3_memory_bridge_benchmark.sv']
if args.fec:
    sources[-1]='experiments/s3_memory_fec_benchmark.sv'
    sys.path.insert(0,str(ROOT/'experiments'))
    from s3_tc8psk import source as tc_source
    from s3_rs_isdb import source as rs_source
    (out/'viterbi.sv').write_text(tc_source())
    (out/'rs.sv').write_text(rs_source(True))
    sources+=['rtl/s3_tc8psk_metric.sv',str((out/'viterbi.sv').relative_to(ROOT)),str((out/'rs.sv').relative_to(ROOT))]
hashes={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources}
if (out/'result.json').exists():
    old=json.loads((out/'result.json').read_text())
    key=hashlib.sha256(json.dumps(old,sort_keys=True).encode()).hexdigest()[:12]
    trial=out/'trials'/key;trial.mkdir(parents=True,exist_ok=True)
    for f in ('result.json','synth.log','pnr.log','stat.json'):
        if (out/f).exists():shutil.copy2(out/f,trial/f)
(out/'synth.ys').write_text('read_verilog -sv '+' '.join(sources)+'\n'+
    'synth_gowin -top '+top+' -family gw1n -nowidelut -json '+str(out/'design.json')+'\n'+
    'tee -o '+str(out/'stat.json')+' stat -json\ncheck -assert\n')
with (out/'synth.log').open('w') as f:
    rc=subprocess.run(['yosys','-Q','-T','-s',str(out/'synth.ys')],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT).returncode
if rc:raise RuntimeError('synthesis failed: '+str(out/'synth.log'))
modules=json.loads((out/'design.json').read_text())['modules']
tops=[m for m in modules.values() if int(str(m.get('attributes',{}).get('top','0')),2)]
if len(tops)!=1:raise ValueError('ambiguous top')
design=tops[0]
buf=[c for c in design['cells'].values() if c['type']=='IBUF' and c['connections']['I']==design['ports']['clk27']['bits']]
aliases=[n for n,v in design['netnames'].items() if v['bits']==buf[0]['connections']['O'] and not n.startswith('$')]
clock=min(aliases,key=len)
def net_alias(bits):
    aliases=[n for n,v in design['netnames'].items() if v['bits']==bits and not n.startswith('$')]
    if not aliases:raise ValueError('missing clock net alias')
    return min(aliases,key=len)
pll=[c for c in design['cells'].values() if c['type']=='rPLL']
if len(pll)!=1:raise ValueError('expected one PLL')
clock_pairs=[(clock,27)]+[(net_alias(pll[0]['connections'][port]),99) for port in ('CLKOUT','CLKOUTP')]
if args.bridge:
    for port in ('spi2_sclk','spi3_sclk'):
        ib=[c for c in design['cells'].values() if c['type']=='IBUF' and c['connections']['I']==design['ports'][port]['bits']]
        gb=[c for c in design['cells'].values() if c['type']=='BUFG' and c['connections']['I']==ib[0]['connections']['O']]
        clock_pairs.append((net_alias(gb[0]['connections']['O']),80))
clocks=''.join(f'ctx.addClock({net!r},{freq})\n' for net,freq in clock_pairs)
(out/'clocks.py').write_text(clocks)
cst='experiments/s3_psram_benchmark.cst'
if args.bridge:
    cst=str(out/'pins.cst')
    (out/'pins.cst').write_text((ROOT/'experiments/s3_spi_rx_benchmark.cst').read_text().replace('"clk"','"clk27"'))
trials=[];report={}
for seed in args.seeds:
    log=out/f'pnr-seed{seed}.log';rp=out/f'report-seed{seed}.json'
    rp.unlink(missing_ok=True)
    with log.open('w') as f:
        try:
            rc=subprocess.run(['nextpnr-himbaechel','--json',str(out/'design.json'),
                '--device','GW1NR-LV9QN88PC6/I5','--vopt','family=GW1N-9C',
                '--vopt','cst='+cst,'--freq','99',
                '--pre-pack',str(out/'clocks.py'),'--seed',str(seed),'--report',str(rp),
                '--placer',args.placer,'--placer-heap-cell-placement-timeout',str(args.heap_cell_timeout),
                '--write',str(out/'routed.json')],
                cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=args.pnr_timeout).returncode
        except subprocess.TimeoutExpired:
            rc=124;f.write(f'\nERROR: P&R timed out after {args.pnr_timeout} seconds; fit remains unknown\n')
    report=json.loads(rp.read_text()) if rp.exists() else {}
    notes=[l for l in log.read_text().splitlines() if l.startswith(('Warning:','ERROR:'))]
    packed={n:dict(used=int(u),available=int(v)) for n,u,v in re.findall(r'Info:\s+(\w+):\s+(\d+)/\s+(\d+)',log.read_text())}
    trials.append(dict(seed=seed,exit_code=rc,fmax=report.get('fmax'),notes=notes,
                       preplacement_utilization=packed,timeout_seconds=args.pnr_timeout,
                       placer=args.placer,heap_cell_timeout=args.heap_cell_timeout))
    shutil.copy2(log,out/'pnr.log')
    if rc==0 or any('ERROR:' in l and 'Max frequency' not in l for l in notes):break
result=dict(scope=__doc__,variant=name,exit_code=rc,sources=hashes,clock_constraints=clock_pairs,
    synthesis=json.loads((out/'stat.json').read_text()),pnr_trials=trials,
    utilization=report.get('utilization'),fmax=report.get('fmax'),
    physical_timing_proven=False,receiver_adopted=False,safe_to_flash=False,
    absent=['validated DQ/RWDS sampling eye','phase-related external IO STA','full receiver integration','real hardware BIST'])
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
(ROOT/f'reports/{name}.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('exit_code','pnr_trials','utilization')},indent=2))

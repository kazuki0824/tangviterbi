#!/usr/bin/env python3
"""Synthesize implemented communication pieces; do not label this full RX fit."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
results={}
for name,top,paths,params in (
 ('iq10','s3_iq10_unpack',['rtl/s3_iq10_unpack.sv'],''),
 ('spi8','s3_spi_rx',['rtl/s3_async_fifo.sv','rtl/s3_spi_rx.sv'],'chparam -set LANES 8 s3_spi_rx'),
 ('spi4','s3_spi_rx',['rtl/s3_async_fifo.sv','rtl/s3_spi_rx.sv'],'chparam -set LANES 4 s3_spi_rx'),
 ('guard','s3_page_guard',['rtl/s3_page_guard.sv'],''),
 ('order','s3_page_reorder',['rtl/s3_page_reorder.sv'],''),
 ('store','s3_rx_page_store',['rtl/s3_page_guard.sv','rtl/s3_page_reorder.sv','rtl/s3_rx_page_store.sv'],''),
 ('iqtx4','s3_spi_iq_tx',['rtl/s3_spi_iq_tx.sv'],''),
 ('iqtx4_pingpong','s3_spi_iq_pingpong',['rtl/s3_spi_iq_pingpong.sv'],'')):
 out=ROOT/'build/s3-comm-area'/name;out.mkdir(parents=True,exist_ok=True)
 script='read_verilog -sv '+' '.join(paths)+'\n'+params+'\nsynth_gowin -family gw1n -top '+top+' -noiopads -nowidelut\ntee -o '+str(out/'stat.json')+' stat -json\ncheck -assert\n'
 (out/'synth.ys').write_text(script)
 with (out/'synth.log').open('w') as f:subprocess.run(['yosys','-Q','-T','-s',str(out/'synth.ys')],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
 s=json.loads((out/'stat.json').read_text());cells=s['design']['num_cells_by_type']
 results[name]=dict(cells=cells,logic_equivalents=sum(v for k,v in cells.items() if k.startswith('LUT') or k=='ALU'),
    FF=sum(v for k,v in cells.items() if k.startswith('DFF')),BSRAM=sum(v for k,v in cells.items() if k in ('DP','SDP','SDPB','SP','DPB','SPB','SDPX9B','DPX9B','SPX9B')),
    creator=s['creator'],sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
report=dict(scope='Module synthesis of RX wire+CDC, guard, reorder/write arbiter, native unpack and IQ TX. No physical PSRAM/status/full demodulator; module areas are not integrated fit or timing proof.',modules=results,receiver_adopted=False)
p=ROOT/'reports/s3-comm-area.json';p.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

# Pin-constrained two-port RX placement benchmark. Constrain INTERNAL IBUF
# output nets: constraints on external pad nets are not propagated by this flow.
out=ROOT/'build/s3-comm-pnr';out.mkdir(parents=True,exist_ok=True)
(out/'clocks.py').write_text('ctx.addClock("g[0].guard.clk",99)\nctx.addClock("p2.spi_clk",80)\nctx.addClock("p3.spi_clk",80)\n')
(out/'synth.ys').write_text('read_verilog -sv rtl/s3_async_fifo.sv rtl/s3_spi_rx.sv rtl/s3_page_guard.sv experiments/s3_spi_rx_benchmark.sv\nsynth_gowin -top s3_spi_rx_benchmark -family gw1n -nowidelut -json build/s3-comm-pnr/design.json\ncheck -assert\n')
with (out/'synth.log').open('w') as f:subprocess.run(['yosys','-Q','-T','-s',str(out/'synth.ys')],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
with (out/'pnr.log').open('w') as f:
 rc=subprocess.run(['nextpnr-himbaechel','--json',str(out/'design.json'),'--device','GW1NR-LV9QN88PC6/I5','--vopt','family=GW1N-9C','--vopt','cst=experiments/s3_spi_rx_benchmark.cst','--freq','99','--pre-pack',str(out/'clocks.py'),'--seed','1','--report',str(out/'report.json')],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT).returncode
pnr=json.loads((out/'report.json').read_text()) if (out/'report.json').exists() else {}
report['RX_pin_placement']=dict(exit_code=rc,fmax=pnr.get('fmax'),utilization=pnr.get('utilization'),
 source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ('experiments/s3_spi_rx_benchmark.sv','experiments/s3_spi_rx_benchmark.cst')},
 scope='Two RX ports with per-port guards and checksum sinks. Clock targets 99/80/80 MHz; core PLL and external IO delay/CDC skew constraints are not included. No full receiver claim.')
p.write_text(json.dumps(report,indent=2)+'\n')

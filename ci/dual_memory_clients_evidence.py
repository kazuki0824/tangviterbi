#!/usr/bin/env python3
"""Synthesize connected memory clients and packed FIFO; no full receiver STA."""
import argparse,gzip,hashlib,json,subprocess
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PREFIX='''module top(input wire core_clk,mem_clk,resetn,output wire activity);
reg[255:0] stimulus=256'h8128643212344321;
always @(posedge mem_clk)if(!resetn)stimulus<=256'h8128643212344321;
else stimulus<={stimulus[254:0],stimulus[255]^stimulus[253]^stimulus[250]^stimulus[245]};
'''
TOPS={
'vector':'''wire vr,ir,ov,done,fault,qv,qr,qw,sr;wire[7:0] od;wire[20:0] qa;wire[255:0] qd;wire[31:0] qm;
dual_vector_exchange v(mem_clk,resetn,stimulus[0],vr,stimulus[23:1],stimulus[39:24],
stimulus[40],ir,stimulus[48:41],ov,stimulus[49],od,done,fault,
qv,stimulus[50],qw,qa,qd,qm,stimulus[51],sr,stimulus);
assign activity=^{vr,ir,ov,done,fault,qv,qw,sr,od,qa,qd,qm};
''',
'fifo':'''wire ready,valid,wr;wire[20:0] addr;wire[255:0] data;wire[31:0] mask;wire[15:0] level;
dual_burst_fifo #(.DEPTH(256)) fifo(mem_clk,resetn,stimulus[0],ready,stimulus[1],stimulus[22:2],stimulus,stimulus[95:64],
valid,stimulus[23],wr,addr,data,mask,level);
assign activity=^{ready,valid,wr,addr,data,mask,level};
''',
'clients':'''wire busy,done,ffault,clip,tr,trv,sr,srv,init,mfault,cke,oe;
wire[255:0] td,sd;wire[2:0] cmd;wire[1:0] bank;wire[10:0] addr;wire[3:0] dqm;wire[31:0] dout;wire[15:0] level;
dual_fft_memory_clients #(.INIT_CYCLES(27000)) mem(core_clk,mem_clk,resetn,stimulus[0],stimulus[4:1],21'd0,21'd8192,21'd16384,
busy,done,ffault,clip,stimulus[5],tr,stimulus[6],{stimulus[24:7],3'd0},stimulus,trv,stimulus[25],td,
init,mfault,cmd,bank,addr,cke,dqm,oe,dout,stimulus[63:32],stimulus[95:64],level,
stimulus[26],sr,stimulus[27],{stimulus[45:28],3'd0},stimulus,stimulus[127:96],srv,stimulus[46],sd);
assign activity=^{busy,done,ffault,clip,tr,trv,sr,srv,init,mfault,cke,oe,td,sd,cmd,bank,addr,dqm,dout,level};
'''}
def main():
    p=argparse.ArgumentParser();p.add_argument('--yosys',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--components',default='fifo,clients,vector');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);rows=[]
    for name in a.components.split(','):
        top=TOPS[name]
        folder=ROOT/'build'/'memory-clients-synth'/name;folder.mkdir(parents=True,exist_ok=True)
        (folder/'top.sv').write_text(PREFIX+top+'endmodule\n')
        files=([ROOT/'rtl/dual_vector_exchange.sv'] if name=='vector' else [ROOT/'rtl/dual_burst_fifo.sv'] if name=='fifo' else
               sorted((ROOT/'rtl').glob('dual_fft_*.sv'))+sorted((ROOT/'rtl').glob('dual_burst_*.sv'))+[ROOT/'rtl/dual_sdram_burst.sv'])
        files+=[folder/'top.sv']
        script='read_verilog -sv '+' '.join(map(str,files))+f'\nsynth_gowin -family gw2a -top top -nowidelut -json {folder}/design.json\ncheck -assert\n'
        (folder/'synth.ys').write_text(script)
        with (folder/'synth.log').open('w') as log:
            r=subprocess.run([a.yosys,'-Q','-s',str(folder/'synth.ys')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        row=dict(component=name,exit_code=r.returncode,scope=('Observable synthetic wrapper including 256-bit stimulus. Vector descriptor and stream inputs variable. Not full receiver, pin fit, or STA.' if name=='vector' else 'Observable synthetic wrapper including 256-bit stimulus. Fixed frame bases, variable FFT mode. Not full receiver, pin fit, or STA.'))
        if r.returncode==0:
            design=json.loads((folder/'design.json').read_text());counts=Counter(c['type'] for c in design['modules']['top']['cells'].values())
            row['cells']=dict(sorted(counts.items()));row['logic_positions_LUT_plus_ALU']=sum(n for t,n in counts.items() if t.startswith('LUT') or t=='ALU')
        row['source_sha256']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files+[Path(__file__),ROOT/'rtl/dual_fft_quarter_q16.hex']}
        rows.append(row)
        for filename in ('top.sv','synth.ys','synth.log'):
            (a.output/f'{name}-{filename}.gz').write_bytes(gzip.compress((folder/filename).read_bytes(),mtime=0))
        print(json.dumps(row),flush=True)
    (a.output/'summary.json').write_text(json.dumps(dict(components=rows,toolchain='OSS CAD Suite 2026-10-04',full_receiver_adopted=False),indent=2)+'\n')
if __name__=='__main__':main()

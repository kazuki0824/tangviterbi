#!/usr/bin/env python3
"""Reproduce partial GW2A placement/resource evidence with explicit STA gaps.

These synthetic observable workloads are NOT a connected receiver or bitstream
for the 27 MHz oscillator. The external clock port models the internal target
clock. PLL, external SDRAM IO timing, CDC and receiver scheduling are absent.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from s3_rs_isdb import source
GAP_SOURCE='https://github.com/YosysHQ/nextpnr/blob/e2fe86b3/himbaechel/uarch/gowin/gowin_arch_gen.py'
PREFIX='''module top(input wire clk,resetn,output wire activity);
 reg[255:0] lfsr=256'h8128643212344321;
 always @(posedge clk)if(!resetn)lfsr<=256'h8128643212344321;
 else lfsr<={lfsr[254:0],lfsr[255]^lfsr[253]^lfsr[250]^lfsr[245]};
'''
TOPS={
'fft':'''wire lr,busy,done,rv,overflow;wire[31:0] rd;wire[5:0] phase;
 wire signed[17:0] wr,wi;wire ci,cv,cf;wire[31:0] cd;
 wire mv;wire[20:0] ma;wire[9:0] mi;wire[12:0] mp;wire[2:0] mk,ml;wire[7:0] mc;
 dual_fft_burst_map mapper(lfsr[3:0],lfsr[4],lfsr[5],{lfsr[49:32],3'd0},lfsr[68:64],lfsr[79:72],lfsr[82:80],mv,ma,mi,mp,mk,ml,mc);
 wire[12:0] wphase=busy ? {1'b0,phase,6'd0} : lfsr[12:0];
 dual_fft_twiddle tw(clk,wphase,wr,wi);
 dual_fft_tile tile(clk,resetn,lfsr[130:128],lfsr[133:131],lfsr[1],lfsr[2],lfsr[3],lr,lfsr[13:4],lfsr[63:32],lfsr[14],busy,done,
 lfsr[15],lfsr[25:16],rv,rd,phase,wr,wi,overflow);
 dual_fft_cross cross_unit(clk,resetn,!busy&&lfsr[3],ci,lfsr[95:80],lfsr[127:112],wr,wi,cv,lfsr[14],cd,cf);
 assign activity=^{lr,busy,done,rv,overflow,rd,ci,cv,cf,cd,mv,ma,mi,mp,mk,ml,mc};
''',
'rs':'''wire[2:0] ready,grant;wire v,first,last,fail;wire[1:0] owner;wire[7:0] data;
 dual_shared_rs rs(clk,resetn,lfsr[2:0],lfsr[5:3],lfsr[63:40],ready,grant,v,first,last,fail,owner,data);
 assign activity=^{ready,grant,v,first,last,fail,owner,data};
''',
'sdram':'''wire ready,valid,init,fault,cke,oe;wire[255:0] data;wire[2:0] cmd;
 wire[1:0] bank;wire[10:0] addr;wire[3:0] mask;wire[31:0] dout;
 dual_sdram_burst mem(clk,resetn,lfsr[0],ready,lfsr[1],{lfsr[20:3],3'd0},lfsr,lfsr[95:64],
 valid,lfsr[2],data,init,fault,cmd,bank,addr,cke,mask,oe,dout,lfsr[63:32]);
 assign activity=^{ready,valid,data,init,fault,cmd,bank,addr,cke,mask,oe,dout};
'''}
FILES={'fft':['dual_fft_tile.sv','dual_fft_cross.sv','dual_fft_twiddle.sv','dual_fft_burst_map.sv'],
       'rs':['dual_shared_rs.sv'],'sdram':['dual_sdram_burst.sv']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--yosys',default='yosys');p.add_argument('--nextpnr',default='nextpnr-himbaechel');a=p.parse_args()
    rows=[];a.output.mkdir(parents=True,exist_ok=True)
    for tag in ('fft','rs','sdram'):
        b=ROOT/'build/dual-components'/tag;b.mkdir(parents=True,exist_ok=True)
        (b/'top.sv').write_text(PREFIX+TOPS[tag]+'endmodule\n')
        files=[ROOT/'rtl'/n for n in FILES[tag]]+[b/'top.sv']
        if tag=='rs':
            (b/'decoder.sv').write_text(source(True,False));files.append(b/'decoder.sv')
        script='read_verilog -sv '+' '.join(map(str,files))+f'\nsynth_gowin -family gw2a -top top -nowidelut -json {b}/design.json\ncheck -assert\n'
        (b/'synth.ys').write_text(script)
        with (b/'synth.stdout').open('w') as log:
            subprocess.run([a.yosys,'-Q','-l',str(b/'synth.log'),'-s',str(b/'synth.ys')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        with (b/'pnr.log').open('w') as log:
            run=subprocess.run([a.nextpnr,'--json',str(b/'design.json'),'--write',str(b/'routed.json'),
                '--device','GW2AR-LV18QN88C8/I7','--vopt','family=GW2A-18C','--vopt',f'cst={ROOT}/constraints/tangnano20k.cst',
                '--freq','135' if tag=='sdram' else '162','--seed','1','--report',str(b/'report.json')],stdout=log,stderr=subprocess.STDOUT,timeout=300)
        raw=json.loads((b/'report.json').read_text()) if (b/'report.json').exists() else {}
        util=raw.get('utilization',{})
        log=(b/'pnr.log').read_text();routed='Program finished normally' in log or 'Max frequency' in log and 'Routing time' in log
        rows.append(dict(component=tag,exit_code=run.returncode,routing_completed=routed,
            reported_partial_fmax=raw.get('fmax'),utilization=util,
            routed_logic_positions=util.get('LUT4',{}).get('used',0)+util.get('ALU',{}).get('used',0),
            full_domain_STA_qualified=False,
            source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files+([ROOT/'rtl/dual_fft_quarter_q16.hex'] if tag=='fft' else [])},
            scope='Synthetic observable component workload, including a 256-bit stimulus register. Not full receiver/PHY/PLL timing.'))
        for name in ('synth.log','pnr.log','report.json','top.sv'):
            f=b/name
            if f.exists():
                with (a.output/f'{tag}-{name}.gz').open('wb') as target:target.write(gzip.compress(f.read_bytes(),mtime=0))
    result=dict(toolchain='OSS CAD Suite 2026-10-04, nextpnr e2fe86b3',components=rows,
        timing_model_gaps=dict(source=GAP_SOURCE,
            findings=['No DSP/MULT timing group in GW2A-18C packaged database or create_timing_info.',
                      'DP port-B output arc is named DO instead of DOB; ADB timing is attached to sp instead of dp.'],
            consequence='Do not treat reported MHz/PASS as coverage of BRAM-to-DSP-to-BRAM or all RS RAM paths. Vendor STA or a validated complete timing model required.'),
        full_receiver_adopted=False)
    (a.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()

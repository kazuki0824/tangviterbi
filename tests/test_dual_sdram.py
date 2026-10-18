"""Pin-command SDRAM protocol simulation, independent memory/scoreboard.

Declared cycle timing inputs, not analog/IO calibration or silicon validation.
"""
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
BENCH=r'''`timescale 1ns/1ps
module tb;
parameter REQUESTS=1,OPEN_PAGE=1,MEM_WORDS=32768;
parameter RSTART=128,RSTOP=383,WSTART=384,WSTOP=639;
reg clk=0;always #5 clk=~clk;
reg resetn=0,valid=0;wire ready,rv,initialized,fault;
reg wr=0;reg[20:0] addr=0;reg[255:0] data=0;reg[31:0] masks=0;
wire[255:0] response;wire[2:0] cmd;wire[1:0] bank;wire[10:0] a;
wire cke,oe;wire[3:0] dqm;wire[31:0] dout;reg[31:0] din=0;
reg types[0:REQUESTS-1];reg[20:0] addresses[0:REQUESTS-1];
reg[255:0] inputs[0:REQUESTS-1],expected[0:REQUESTS-1];reg[31:0] maskdata[0:REQUESTS-1];
reg[31:0] mem[0:MEM_WORDS-1];reg[3:0] opened=0;
integer rows[0:3],activated[0:3],precharged[0:3],lastwrite[0:3];
integer cycle=0,refs=0,mode_at=-10000,lastref=-10000,read_at=-10000,read_base=0;
integer wleft=0,waddr=0,wbank=0,received=0,sent=0,i,j,base;
integer rbegin=-1,rend=-1,wbegin=-1,wend=-1,max_ref_gap=0;
reg[255:0] held;reg holding=0;
wire rsp_ready=!(cycle>=1000 && cycle<4000);
dual_sdram_burst #(.INIT_CYCLES(32),.OPEN_PAGE(OPEN_PAGE)) dut(
 clk,resetn,valid,ready,wr,addr,data,masks,rv,rsp_ready,response,initialized,fault,
 cmd,bank,a,cke,dqm,oe,dout,din);
always @(negedge clk)begin
 if(cycle+1>=read_at && cycle+1<read_at+8)din=mem[read_base+cycle+1-read_at];else din=0;
end
always @(posedge clk)begin
 cycle=cycle+1;
 if(resetn)begin
  if(fault)$fatal(1,"controller fault");
  if(valid && ready)begin
   if(sent==RSTART)rbegin=cycle;
   if(sent==WSTART)wbegin=cycle;
   sent=sent+1;
  end
  if(holding && (!rv || response!==held))$fatal(1,"response changed under backpressure");
  holding=rv&&!rsp_ready;held=response;
  if(rv && rsp_ready)begin
   if(received>=REQUESTS || response!==expected[received])$fatal(1,"response mismatch %0d",received);
   if(received==RSTOP)rend=cycle;
   if(received==WSTOP)wend=cycle;
   received=received+1;
  end
  if(wleft>0)begin
   if(!oe)$fatal(1,"write burst has hole");
   for(j=0;j<4;j=j+1)if(!dqm[j])mem[waddr][j*8+:8]=dout[j*8+:8];
   lastwrite[wbank]=cycle;wleft=wleft-1;waddr=waddr+1;
  end
  if(cycle>=read_at && cycle<read_at+8 && oe)$fatal(1,"DQ collision");
  if(cmd!=7 && cycle-lastref<10)$fatal(1,"tRFC violation");
  case(cmd)
   0:begin
    if(refs<8 || a!=11'h33 || bank!=0)$fatal(1,"bad mode/init sequence");
    mode_at=cycle;
   end
   1:begin
    if(opened!=0)$fatal(1,"refresh on open row");
    if(refs>=8 && cycle-lastref>max_ref_gap)max_ref_gap=cycle-lastref;
    if(refs>=9 && cycle-lastref>1053)$fatal(1,"refresh deadline missed");
    lastref=cycle;refs=refs+1;
   end
   2:begin
    for(j=0;j<4;j=j+1)if(a[10] || j==bank)begin
     if(opened[j] && (cycle-activated[j]<6 || cycle-lastwrite[j]<3))$fatal(1,"tRAS/tWR violation");
     opened[j]=0;precharged[j]=cycle;
    end
   end
   3:begin
    if(opened[bank] || cycle-precharged[bank]<3 || cycle-mode_at<3)$fatal(1,"bad activate");
    opened[bank]=1;rows[bank]=a;activated[bank]=cycle;
   end
   4,5:begin
    if(!opened[bank] || cycle-activated[bank]<3 || a[10])$fatal(1,"bad column command");
    base=(rows[bank]*4+bank)*256+a[7:0];
    if(base!=addresses[received] || base+7>=MEM_WORDS)$fatal(1,"wrong physical address");
    if(cmd==4)begin
     if(!oe)$fatal(1,"missing first write");
     for(j=0;j<4;j=j+1)if(!dqm[j])mem[base][j*8+:8]=dout[j*8+:8];
     lastwrite[bank]=cycle;wleft=7;waddr=base+1;wbank=bank;
    end else begin read_base=base;read_at=cycle+3;end
   end
  endcase
  if(received==REQUESTS)begin
   if(refs<10)$fatal(1,"refresh under response stall not exercised");
   $display("PASS requests=%0d refreshes=%0d max_refresh_gap=%0d read_cycles=%0d write_cycles=%0d",received,refs,max_ref_gap,rend-rbegin,wend-wbegin);
   $finish;
  end
  if(cycle>300000)$fatal(1,"deadlock");
 end
end
initial begin
 for(i=0;i<MEM_WORDS;i=i+1)mem[i]=0;
 for(i=0;i<4;i=i+1)begin rows[i]=0;activated[i]=-10000;precharged[i]=-10000;lastwrite[i]=-10000;end
 $readmemh("types.hex",types);$readmemh("addresses.hex",addresses);$readmemh("inputs.hex",inputs);
 $readmemh("masks.hex",maskdata);$readmemh("expected.hex",expected);
 repeat(3)@(negedge clk);resetn=1;
 for(i=0;i<REQUESTS;i=i+1)begin
  @(negedge clk);valid=1;wr=types[i];addr=addresses[i];data=inputs[i];masks=maskdata[i];
  @(posedge clk);while(!ready)@(posedge clk);
 end
 @(negedge clk);valid=0;
end
endmodule
'''

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class SDRAMTest(unittest.TestCase):
    def test_protocol_data_masks_refresh_and_backpressure(self):
        rng=random.Random(0x64135);requests=[];memory={}
        def write(a):
            words=[rng.getrandbits(32) for _ in range(8)];masks=rng.getrandbits(32)
            data=sum(v<<(32*i) for i,v in enumerate(words))
            for i,v in enumerate(words):
                old=memory.get(a+i,0)
                for b in range(4):
                    if not(masks>>(i*4+b))&1:old=(old&~(255<<(8*b)))|(v&(255<<(8*b)))
                memory[a+i]=old
            requests.append((1,a,data,masks,0))
        def read(a):requests.append((0,a,0,0,sum(memory.get(a+i,0)<<(32*i) for i in range(8))))
        for i in range(64):write(i*128)
        setup_memory=dict(memory)
        for i in reversed(range(64)):read(i*128)
        for i in range(256):read((i%32)*8)
        for i in range(256):write((i%32)*8)
        traces=[('same_row',requests,128,383,384,639)]
        # Fully backlogged Mode-3 FFT traffic, including input write and output
        # read. Two passes use the exact 8-word row/column burst mapping.
        # This is a serialization witness, NOT a real-time multi-client arbiter.
        requests=requests[:128]
        memory=dict(setup_memory)
        mixed_start=len(requests)
        for a in range(0,8192,8):write(a)
        for tile in range(8):
            for row in range(128):read(row*64+tile*8)
            for row in range(128):write(8192+row*64+tile*8)
        for tile in range(8):
            for lane in range(16):
                for point in range(0,64,8):read(8192+(tile*16+lane)*64+point)
            for point in range(64):
                for lane in range(0,16,8):write(16384+point*128+tile*16+lane)
        for a in range(16384,24576,8):read(a)
        mixed_stop=len(requests)-1
        # Repeat a direction-changing row-conflict sequence in all four banks.
        conflict_start=len(requests)
        for i in range(512):
            a=(i%4)*256+((i//4)%2)*1024
            if i%2:write(a)
            else:read(a)
        traces.append(('fft_mode3_and_conflicts',requests,mixed_start,mixed_stop,conflict_start,len(requests)-1))
        results=[]
        for tag,requests,rstart,rstop,wstart,wstop in traces:
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp);(p/'tb.sv').write_text(BENCH)
                for index,name in enumerate(('types','addresses','inputs','masks','expected')):
                    (p/f'{name}.hex').write_text('\n'.join(f'{row[index]:x}' for row in requests)+'\n')
                for opened in (0,1):
                    subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.REQUESTS={len(requests)}',f'-Ptb.OPEN_PAGE={opened}',f'-Ptb.RSTART={rstart}',f'-Ptb.RSTOP={rstop}',f'-Ptb.WSTART={wstart}',f'-Ptb.WSTOP={wstop}',
                        '-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_sdram_burst.sv')],check=True,timeout=30)
                    r=subprocess.run(['vvp',str(p/'sim')],cwd=p,text=True,capture_output=True,timeout=60)
                    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                    line=next(x for x in r.stdout.splitlines() if x.startswith('PASS'))
                    metrics={k:int(v) for k,v in (x.split('=') for x in line.split()[1:])}
                    metrics.update(trace=tag,open_page=bool(opened),first_phase_bursts=rstop-rstart+1,second_phase_bursts=wstop-wstart+1,first_phase_MBps=(rstop-rstart+1)*32*135/metrics['read_cycles'],second_phase_MBps=(wstop-wstart+1)*32*135/metrics['write_cycles'])
                    results.append(metrics)
        if os.environ.get('DUAL_SDRAM_REPORT'):
            Path(os.environ['DUAL_SDRAM_REPORT']).write_text(json.dumps(dict(results=results,
                source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'rtl/dual_sdram_burst.sv',Path(__file__))},
                clock_MHz_assumed=135,CL=3,TRCD=3,TRP=3,TWR=3,TRFC=10,TMRD=3,refresh_cycles=1053,
                qualification='Independent digital command model, INIT shortened to 32 cycles. Timing inputs are unqualified for silicon; PHY/CDC and concurrent client arbitration absent.'),indent=2)+'\n')
if __name__=='__main__':unittest.main()

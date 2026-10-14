"""Compact vectors: every alignment, adjacent masked bytes, and stalled consumers."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BENCH=r'''`timescale 1ns/1ps
module tb;
reg clk=0,resetn=0;always #5 clk=~clk;
reg vv=0;wire vr,ir,ov,done,fault,qv,qw,sr;
reg [22:0] addr;reg [15:0] len;
integer cycle=0,sent=0,got=0,trial=0,j,b,delay=0;
reg [7:0] mem[0:4095];reg [7:0] expected[0:1023];reg [7:0] before_mem[0:4095];
wire iv=sent<len && cycle%7!=0;
wire [7:0] id=(sent*17+trial*31);
wire ordy=cycle%43>19;
wire [7:0] od;
wire qr=!pending && cycle%11>3;
wire [20:0] qa;wire [255:0] qd;wire [31:0] qm;
reg pending=0,sv=0;reg [255:0] sd;
reg hold=0;reg [309:0] saved;
reg oh=0;reg [7:0] os;
dual_vector_exchange dut(clk,resetn,vv,vr,addr,len,iv,ir,id,ov,ordy,od,
 done,fault,qv,qr,qw,qa,qd,qm,sv,sr,sd);
always @(posedge clk)if(resetn)begin
 cycle<=cycle+1;
 if(hold && (!qv||{qw,qa,qd,qm}!==saved))$fatal(1,"request changed");
 hold<=qv&&!qr;saved<={qw,qa,qd,qm};
 if(oh&&(!ov||od!==os))$fatal(1,"output changed");
 oh<=ov&&!ordy;os<=od;
 if(iv&&ir)sent<=sent+1;
 if(ov&&ordy)begin
  if(od!==expected[got])$fatal(1,"old byte mismatch trial=%0d byte=%0d",trial,got);
  got<=got+1;
 end
 if(qv&&qr)begin
  if(qa[2:0]!=0)$fatal(1,"unaligned burst");
  if(qw && got<sent)$fatal(1,"overwritten before output accepted");
  for(b=0;b<32;b=b+1)begin
   if(qw)begin if(!qm[b])mem[qa*4+b]=qd[b*8+:8];end
   else sd[b*8+:8]<=mem[qa*4+b];
  end
  pending<=1;delay<=1+cycle%13;
 end
 if(pending&&!sv)begin
  if(delay==0)sv<=1;else delay<=delay-1;
 end
 if(sv&&sr)begin sv<=0;pending<=0;end
 if(cycle>500000)$fatal(1,"timeout");
end
initial begin
 addr=0;len=0;for(j=0;j<4096;j=j+1)mem[j]=(j*13+9)%256;
 #32;resetn=1;
 for(trial=0;trial<128;trial=trial+1)begin
  @(negedge clk);addr=1024+trial%32;
  case(trial/32)0:len=1;1:len=32;2:len=33;3:len=773;endcase
  for(j=0;j<4096;j=j+1)before_mem[j]=mem[j];
  for(j=0;j<len;j=j+1)expected[j]=mem[addr+j];
  sent=0;got=0;vv=1;
  @(negedge clk);vv=0;
  wait(done);@(negedge clk);
  if(got!=len||sent!=len||fault)$fatal(1,"count/fault");
  for(j=0;j<4096;j=j+1)begin
   if(j>=addr&&j<addr+len)begin
    if(mem[j]!==8'((j-addr)*17+trial*31))$fatal(1,"write byte mismatch");
   end else if(mem[j]!==before_mem[j])$fatal(1,"adjacent byte overwritten");
  end
 end
 // Invalid descriptors must cause no memory access.
 @(negedge clk);addr=23'h7fffff;len=2;vv=1;
 @(negedge clk);vv=0;
 if(!fault||!vr||qv)$fatal(1,"overflow not rejected");
 $display("PASS vectors=128 all offsets, stalls, read-before-write");$finish;
end
endmodule
'''
# Reuse the vector scoreboard against pin-visible memory, not request echo.
def pin_bench():
    bench=BENCH.replace("wire qr=!pending && cycle%11>3;", "wire qr;")
    bench=bench.replace("reg pending=0,sv=0;reg [255:0] sd;", "wire sv;wire [255:0] sd;reg pending=0;")
    begin=bench.index(" if(qv&&qr)begin")
    end=bench.index(" if(cycle>500000)",begin)
    bench=bench[:begin]+bench[end:]
    insert=r'''wire initialized,cfault,cke,oe;wire[2:0] cmd;wire[1:0] bank;
wire[10:0] sa;wire[3:0] dqm;wire[31:0] dout;reg[31:0] din=0;
integer rows[0:3],act[0:3],pre[0:3],wrtime[0:3];reg[3:0] opened=0;
integer read_at=-1000,read_base=0,wleft=0,waddr=0,wbank=0,lastref=-1000,refs=0;
integer k,bb,physical;
dual_sdram_burst #(.INIT_CYCLES(32)) controller(clk,resetn,qv,qr,qw,qa,qd,qm,
 sv,sr,sd,initialized,cfault,cmd,bank,sa,cke,dqm,oe,dout,din);
initial for(k=0;k<4;k=k+1)begin rows[k]=0;act[k]=-1000;pre[k]=-1000;wrtime[k]=-1000;end
always @(negedge clk)begin
 din=0;
 if(cycle>=read_at&&cycle<read_at+8)
  for(bb=0;bb<4;bb=bb+1)din[bb*8+:8]=mem[read_base+4*(cycle-read_at)+bb];
end
always @(posedge clk)if(resetn)begin
 if(cfault)$fatal(1,"controller fault");
 if(wleft>0)begin
  if(!oe)$fatal(1,"write hole");
  for(k=0;k<4;k=k+1)if(!dqm[k])mem[waddr+k]=dout[k*8+:8];
  waddr=waddr+4;wleft=wleft-1;wrtime[wbank]=cycle;
 end
 if(cmd!=7&&cycle-lastref<10)$fatal(1,"tRFC");
 case(cmd)
  1:begin
   if(opened!=0)$fatal(1,"refresh open bank");
   if(refs>=9&&cycle-lastref>1053)$fatal(1,"refresh deadline");
   refs=refs+1;lastref=cycle;
  end
  2:for(k=0;k<4;k=k+1)if(sa[10]||k==bank)begin
   if(opened[k]&&(cycle-act[k]<6||cycle-wrtime[k]<3))$fatal(1,"tRAS/tWR");
   opened[k]=0;pre[k]=cycle;
  end
  3:begin
   if(opened[bank]||cycle-pre[bank]<3)$fatal(1,"activate");
   rows[bank]=sa;opened[bank]=1;act[bank]=cycle;
  end
  4,5:begin
   if(!opened[bank]||cycle-act[bank]<3)$fatal(1,"tRCD");
   physical=((rows[bank]*4+bank)*256+sa[7:0])*4;
   if(physical+31>=4096)$fatal(1,"address range");
   if(cmd==4)begin
    if(!oe||got<sent)$fatal(1,"write before output");
    for(k=0;k<4;k=k+1)if(!dqm[k])mem[physical+k]=dout[k*8+:8];
    wleft=7;waddr=physical+4;wbank=bank;wrtime[bank]=cycle;
   end else begin read_at=cycle+3;read_base=physical;end
  end
 endcase
end
'''
    return bench.replace('initial begin\n addr=',insert+'\ninitial begin\n addr=')

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class VectorExchange(unittest.TestCase):
    def run_bench(self, bench, pin=False):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/'tb.sv').write_text(bench)
            subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_vector_exchange.sv')]+([str(ROOT/'rtl/dual_sdram_burst.sv')] if pin else []),check=True)
            r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn('PASS',r.stdout)

    def test_masked_exchange(self):
        self.run_bench(BENCH)

    def test_pin_memory_refresh(self):
        self.run_bench(pin_bench(), pin=True)

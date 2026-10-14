"""Locked-source arbitration, priority changes, and stalled response slots."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BENCH=r'''`timescale 1ns/1ps
module tb;
parameter PRIORITY=0,DIRECT=0;
reg clk=0,resetn=0;always #5 clk=~clk;
integer cyc=0,s0=0,s1=0,r0=0,r1=0,left=0;
wire[1:0] valid,ready,rspv;
assign valid={s1<512&&cyc>=13,s0<512};
wire[1:0] rspr={(cyc%31)>17,(cyc%37)>23};
wire[511:0] rspd;
wire mv,mw,rr;wire[20:0] ma;wire[255:0] md;wire[31:0] mm;
reg rv=0;reg[255:0] rd=0;
wire mr=left==0&&!rv&&(cyc%11)>5;
dual_burst_arbiter #(.PRIORITY_SECOND(PRIORITY),.DIRECT_RESPONSE(DIRECT)) dut(clk,resetn,valid,ready,2'b11,
 {21'(s1*8+8192),21'(s0*8)},{{8{32'(s1+65536)}},{8{32'(s0)}}},
 rspv,rspr,rspd,mv,mr,mw,ma,md,rv,rr,rd,{32'(s1)^32'habcdabcd,32'(s0)^32'h12345678},mm);
reg holding=0;reg[309:0] held;
reg[1:0] rh=0;reg[511:0] rhdata;
always @(posedge clk)if(resetn)begin
 cyc<=cyc+1;
 if(holding&&(!mv||{mw,ma,md,mm}!==held))$fatal(1,"selected request changed while blocked");
 holding=mv&&!mr;held={mw,ma,md,mm};
 for(integer i=0;i<2;i=i+1)if(rh[i]&&(!rspv[i]||rspd[i*256+:256]!==rhdata[i*256+:256]))$fatal(1,"response overwritten");
 rh=rspv&~rspr;rhdata=rspd;
 if(mv&&mr)begin
  if(!mw)$fatal(1,"write bit");
  if(md[31:0]<65536)begin
   if(mm!==(32'(s0)^32'h12345678)||ma!==21'(s0*8))$fatal(1,"T metadata");
  end else if(mm!==(32'(s1)^32'habcdabcd)||ma!==21'(s1*8+8192))$fatal(1,"S metadata");
  rd<=md;left<=7;
 end else if(left>0)begin left<=left-1;if(left==1)rv<=1;end
 if(rv&&rr)rv<=0;
 if(valid[0]&&ready[0])s0<=s0+1;
 if(valid[1]&&ready[1])s1<=s1+1;
 if(rspv[0]&&rspr[0])begin if(rspd[255:0]!=={8{32'(r0)}})$fatal(1,"T order");r0=r0+1;end
 if(rspv[1]&&rspr[1])begin if(rspd[511:256]!=={8{32'(r1+65536)}})$fatal(1,"S order");r1=r1+1;end
 if(r0==512&&r1==512)begin $display("PASS locked arbitration");$finish;end
 if(cyc>100000)$fatal(1,"timeout");
end
initial begin #30;resetn=1;end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class Arbiter(unittest.TestCase):
    def test_locked_sources_and_response_slots(self):
        for priority,direct in ((0,0),(1,0),(1,1)):
            with self.subTest(priority=priority,direct=direct),tempfile.TemporaryDirectory() as temp:
                p=Path(temp);(p/'tb.sv').write_text(BENCH)
                subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.PRIORITY={priority}',f'-Ptb.DIRECT={direct}','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_burst_arbiter.sv')],check=True)
                r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=30)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)

"""Locked request ownership, masked payload, and backpressured response routing."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TB=r'''
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0;reg[5:0]cv=0,cw=0,crr=0;wire[5:0]cr,crv;
reg[125:0]ca=0;reg[1535:0]cd=0;reg[191:0]cm=0;wire[255:0]crd;
wire qv,qw,sr;reg qr=0,sv=0;wire[20:0]qa;wire[255:0]qd;wire[31:0]qm;reg[255:0]sd=0;
integer i;
sdram_client_arbiter dut(clk,resetn,cv,cr,cw,ca,cd,cm,crv,crr,crd,qv,qr,qw,qa,qd,qm,sv,sr,sd);
task check_request;
 input integer who;
 begin
 if(!qv || qa!==21'(who*8) || qd!=={8{32'(who+1)}} || qm!==32'(who*17) || qw!==(who%2))$fatal(1,"request %0d",who);
 end
endtask
task complete;
 input integer who;
 begin
 @(negedge clk);qr=1;#1;check_request(who);
 if(cr!==(6'b1<<who))$fatal(1,"ready owner");
 @(posedge clk);@(negedge clk);qr=0;cv[who]=0;sv=1;sd={8{32'(who+101)}};
 repeat(7)begin
 #1;if(crv!==(6'b1<<who) || crd!==sd || sr || qv || cr)$fatal(1,"response ownership under stall");
 @(negedge clk);
 end
 crr[who]=1;#1;if(!sr)$fatal(1,"response blocked");
 @(posedge clk);@(negedge clk);sv=0;crr=0;
 end
endtask
initial begin
 for(i=0;i<6;i=i+1)begin ca[i*21+:21]=i*8;cd[i*256+:256]={8{32'(i+1)}};cm[i*32+:32]=i*17;cw[i]=i%2;end
 repeat(3)@(negedge clk);resetn=1;cv=1;
 @(posedge clk);@(negedge clk);#1;check_request(0);
 // A new priority request must not replace the already locked descriptor.
 cv=6'b111111;
 repeat(5)begin @(negedge clk);#1;check_request(0);if(cr || crv)$fatal(1,"premature ack");end
 complete(0);
 @(posedge clk);@(negedge clk);#1;check_request(5);complete(5);
 for(i=1;i<5;i=i+1)begin
  @(posedge clk);@(negedge clk);#1;check_request(i);complete(i);
 end
 repeat(3)@(negedge clk);
 if(qv || cr || crv)$fatal(1,"phantom transaction");
 $display("PASS six clients, locked request, seven-cycle response stalls, masks, priority and background RR");$finish;
end
initial begin #100000;$fatal(1,"timeout");end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ArbiterTest(unittest.TestCase):
 def test_locked_request_and_response(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(TB)
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/sdram_client_arbiter.sv')],check=True)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=20)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS six clients',r.stdout)

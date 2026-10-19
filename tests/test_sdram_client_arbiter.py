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
 // Move cursor to 4, then exercise wrap to lower-numbered pending clients.
 cv=6'b010000;@(posedge clk);@(negedge clk);#1;check_request(4);complete(4);
 cv=6'b001000;@(posedge clk);@(negedge clk);#1;check_request(3);complete(3);
 cv=6'b000011;@(posedge clk);@(negedge clk);#1;check_request(0);complete(0);
 @(posedge clk);@(negedge clk);#1;check_request(1);complete(1);
 repeat(3)@(negedge clk);
 if(qv || cr || crv)$fatal(1,"phantom transaction");
 $display("PASS six clients, locked request, seven-cycle response stalls, masks, priority and background RR");$finish;
end
initial begin #100000;$fatal(1,"timeout");end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ArbiterTest(unittest.TestCase):
 rtl_file=ROOT/"rtl/sdram_client_arbiter.sv"
 def test_locked_request_and_response(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(TB)
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(self.rtl_file)],check=True)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=20)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS six clients',r.stdout)

 def test_all_request_subsets_and_cursors(self):
  # Selection oracle is circular search, independent of the mask implementation.
  expected=[]
  for cursor in range(5):
   for valid in range(64):
    selected=32 if valid&32 else next((1<<((cursor+j)%5) for j in range(5) if valid&(1<<((cursor+j)%5))),0)
    expected.append(selected)
  tb=TB[:TB.index('initial begin\n for(i=0;')]+r'''
integer cursor,subset;
initial begin
 resetn=1;
 for(cursor=0;cursor<5;cursor=cursor+1)begin
  for(subset=0;subset<64;subset=subset+1)begin
   dut.rr=cursor;cv=subset;#1;
   $display("SELECT %0d",dut.chosen);
  end
 end
 $finish;
end
endmodule
'''
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(tb)
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(self.rtl_file)],check=True)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=20)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   observed=[int(s.split()[1]) for s in r.stdout.splitlines() if s.startswith('SELECT ')]
   self.assertEqual(observed,expected)

class ArbiterCandidateTest(ArbiterTest):
 rtl_file=ROOT/"experiments/rotation_sdram_client_arbiter.sv"

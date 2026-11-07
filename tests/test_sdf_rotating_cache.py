"""Sequential line contract: word order, reservation, and stalled writeback."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TB=r'''
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,take=0,re=0,we=0,qr=0,rv=0;
reg[11:0]ra=0,wa=0;reg[31:0]wd=0;reg[255:0]rd=0;
wire ready,qv,qw,fault;wire[31:0]out;wire[20:0]qa;wire[255:0]qd;
reg[255:0]expected;integer i;
sdf_delay_cache dut(clk,resetn,take,ready,re,ra,out,we,wa,wd,qv,qr,qw,qa,qd,rv,rd,fault);
task restart;
 begin
 @(negedge clk);resetn=0;take=0;re=0;we=0;qr=0;rv=0;
 repeat(2)@(negedge clk);resetn=1;
 @(negedge clk);if(!qv || qw || qa!=0)$fatal(1,"initial fetch");qr=1;
 @(negedge clk);qr=0;rv=1;
 for(i=0;i<8;i=i+1)rd[i*32+:32]=32'h13579b00+i;
 @(negedge clk);rv=0;
 if(!ready || fault)$fatal(1,"refill reservation");
 end
endtask
initial begin
 restart();expected=0;
 for(i=0;i<8;i=i+1)begin
  if(!ready)$fatal(1,"missing credit");take=1;
  @(negedge clk);take=0;re=1;ra=i;
  if(ready)$fatal(1,"overlapping credit");
  @(negedge clk);re=0;
  if(out!==32'h13579b00+i)$fatal(1,"old word order %0d",i);
  repeat(3)begin @(negedge clk);if(ready)$fatal(1,"early credit");end
  we=1;wa=i;wd=32'hfedcba00+i;expected[i*32+:32]=wd;
  @(negedge clk);we=0;
  if(fault)$fatal(1,"legal access fault");
 end
 repeat(10)begin
  if(!qv || !qw || qa!=0 || qd!==expected || ready)$fatal(1,"writeback changed while stalled");
  @(negedge clk);
 end
 qr=1;@(negedge clk);qr=0;rv=1;
 @(negedge clk);rv=0;
 if(!qv || qw || qa!=8)$fatal(1,"next line ownership");
 restart();take=1;@(negedge clk);take=0;re=1;ra=1;
 @(negedge clk);re=0;if(!fault)$fatal(1,"wrong sequential address accepted");
 restart();we=1;wa=0;wd=123;
 @(negedge clk);we=0;if(!fault)$fatal(1,"unreserved write accepted");
 restart();take=1;@(negedge clk);take=0;we=1;wa=0;
 @(negedge clk);we=0;if(!fault)$fatal(1,"write before read accepted");
 $display("PASS rotation word order, one credit, stalled writeback, next line, negative protocol cases");$finish;
end
initial begin #100000;$fatal(1,"timeout");end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class RotatingCacheTest(unittest.TestCase):
 def test_rotation_and_reservation(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(TB)
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'experiments/rotation_sdf_delay_cache.sv')],check=True)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=20)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS rotation',r.stdout)

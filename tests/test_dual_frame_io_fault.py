"""Framing errors poison an epoch; reset is required before accepting a new one."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BENCH=r'''`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,iv=0,il=0;wire ir,ov,ol,jv,qv,qw,rr,fault;
wire[1:0] js;wire[31:0] od,mask;wire[20:0] addr;wire[255:0] data;wire[8:0] owners;wire[15:0] level;
reg rv=0;wire ready=!rv||rr;
dual_frame_io dut(clk,resetn,iv,ir,32'h12345678,il,ov,1'b1,od,ol,
 jv,1'b0,js,1'b0,1'b0,qv,ready,qw,addr,data,mask,rv,rr,256'd0,owners,level,fault);
always @(posedge clk)if(!resetn)rv<=0;else begin
 if(rv&&rr)rv<=0;
 if(qv&&ready)rv<=1;
end
task restart;begin
 @(negedge clk);iv=0;il=0;resetn=0;
 repeat(3)@(negedge clk);resetn=1;
 if(fault||owners||jv||ov)$fatal(1,"reset failed");
end endtask
task send(input integer words,input integer marker);begin
 for(integer i=0;i<words;i=i+1)begin
  @(negedge clk);iv=1;il=(i==marker);
  @(posedge clk);while(!ir)@(posedge clk);
 end
 @(negedge clk);iv=0;il=0;
end endtask
task poisoned;begin
 repeat(300)@(negedge clk);
 if(!fault||ir||jv||ov)$fatal(1,"bad frame was exposed");
end endtask
initial begin
 restart();send(1,0);poisoned(); // Early marker.
 restart();send(2048,-1);poisoned(); // Missing final marker.
 restart();send(2048,2047);wait(jv);
 if(fault||owners!=2||!ir)$fatal(1,"valid restart frame not committed");
 $display("PASS framing faults and reset recovery");$finish;
end
initial begin #1000000;$fatal(1,"timeout");end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class Faults(unittest.TestCase):
 def test_bad_boundaries_and_reset(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp);(p/'tb.sv').write_text(BENCH)
   files=[ROOT/'rtl'/x for x in ['dual_frame_io.sv','dual_burst_fifo.sv','dual_burst_arbiter.sv']]
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),*map(str,files)],check=True)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=20)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)

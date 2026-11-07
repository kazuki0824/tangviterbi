"""Lease-specific ownership, priority preemption, and quota exhaustion."""
import subprocess,tempfile,unittest,shutil
from pathlib import Path
import test_sdram_client_arbiter as base
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class LeaseTest(base.ArbiterTest):
 rtl_file=ROOT/'experiments/sdram_client_arbiter_tile_grace.sv'
 def test_128_grants_and_fft_preemption(self):
  tb=base.TB[:base.TB.index('initial begin\n for(i=0;')]+r'''
initial begin
 for(i=0;i<6;i=i+1)begin ca[i*21+:21]=i*8;cd[i*256+:256]={8{32'(i+1)}};cm[i*32+:32]=i*17;cw[i]=i%2;end
 repeat(3)@(negedge clk);resetn=1;cv=3;
 for(i=0;i<128;i=i+1)begin
  @(posedge clk);@(negedge clk);#1;check_request(0);complete(0);cv=3;
  if(i==2)begin
   cv=6'b100011;
   @(posedge clk);@(negedge clk);#1;check_request(5);complete(5);cv=3;
  end
 end
 for(i=0;i<128;i=i+1)begin
  @(posedge clk);@(negedge clk);#1;check_request(1);complete(1);cv=3;
 end
 @(posedge clk);@(negedge clk);#1;check_request(0);complete(0);cv=0;
 repeat(3)@(negedge clk);
 if(qv || cr || crv)$fatal(1,"phantom transaction");
 $display("PASS lease128_direct, FFT preemption, quota exhaustion and response stalls");$finish;
end
initial begin #100000;$fatal(1,"timeout");end
endmodule
'''
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(tb)
   r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(self.rtl_file)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=20)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS lease128_direct',r.stdout)

 def run_tb(self,tb):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(tb)
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(self.rtl_file)],check=True)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=20)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)

 def test_locked_request_and_response(self):
  # Only the next client after absent tile gains the specified two-cycle grace.
  tb=base.TB.replace('for(i=1;i<5;i=i+1)begin','for(i=1;i<5;i=i+1)begin\n  if(i==3)repeat(2)@(negedge clk);')
  self.run_tb(tb)

 def test_bounded_grace_and_immediate_fft(self):
  tb=base.TB[:base.TB.index('initial begin\n for(i=0;')]+r'''
initial begin
 for(i=0;i<6;i=i+1)begin ca[i*21+:21]=i*8;cd[i*256+:256]={8{32'(i+1)}};cm[i*32+:32]=i*17;cw[i]=i%2;end
 repeat(3)@(negedge clk);resetn=1;
 dut.state=0;dut.lease=4;dut.remaining=127;dut.grace=0;cv=8;
 #1;if(qv)$fatal(1,"missing initial grace");
 @(posedge clk);@(negedge clk);#1;if(qv)$fatal(1,"missing second grace");
 @(posedge clk);@(negedge clk);#1;check_request(3);
 resetn=0;@(posedge clk);@(negedge clk);resetn=1;
 dut.state=0;dut.lease=4;dut.remaining=127;dut.grace=0;cv=40;
 #1;check_request(5);
 cv=8;#1;if(qv)$fatal(1,"grace lost");
 @(posedge clk);@(negedge clk);cv=12;#1;check_request(2);
 $display("PASS bounded grace, immediate FFT, returning tile");$finish;
end
initial begin #10000;$fatal(1,"timeout");end
endmodule
'''
  self.run_tb(tb)

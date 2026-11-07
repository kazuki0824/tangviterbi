"""Deadline predicates vs the former 16-bit counter, including post-fault saturation.
A forced controller wait isolates the timer and deliberately prevents refresh.
"""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TB=r'''
module tb;
parameter PERIOD=1203;
reg clk=0;always #5 clk=~clk;reg resetn=0;
wire initialized,fault;
integer legacy_age=0,i;reg legacy_fault=0;
dual_sdram_burst #(.INIT_CYCLES(1),.REFRESH_CYCLES(PERIOD),.TRP(1),.TRCD(1),.TRFC(1),.TWR(1),.TMRD(1),.CL(2)) dut(
 .clk(clk),.resetn(resetn),.req_valid(1'b0),.req_write(1'b0),.req_address(21'd0),
 .req_data(256'd0),.req_dqm(32'd0),.rsp_ready(1'b1),.dq_in(32'd0),
 .initialized(initialized),.fault(fault));
initial begin
 repeat(3)@(negedge clk);resetn=1;wait(initialized);@(negedge clk);
 force dut.state=12;force dut.wait_count=16'hffff;
 legacy_age=dut.refresh_age;
 if($bits(dut.refresh_age)!=$clog2(PERIOD+1))$fatal(1,"timer width");
 for(i=0;i<PERIOD+20;i=i+1)begin
  @(posedge clk);
  if(legacy_age>=PERIOD)legacy_fault=1;
  if(legacy_age<65535)legacy_age=legacy_age+1;
  #1;
  if(fault!==legacy_fault)$fatal(1,"fault changed at %0d",i);
  if(dut.refresh_due!==(legacy_age>=PERIOD-32))$fatal(1,"refresh due changed");
 end
 if(!fault || dut.refresh_age!=PERIOD)$fatal(1,"saturation/fault coverage");
 $display("PASS period=%0d width=%0d legacy_age=%0d bounded_age=%0d",PERIOD,$bits(dut.refresh_age),legacy_age,dut.refresh_age);$finish;
end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class RefreshWidthTest(unittest.TestCase):
 def test_thresholds_and_fault_with_parameter_boundaries(self):
  for period in (64,1203,65535):
   with self.subTest(period=period),tempfile.TemporaryDirectory() as d:
    p=Path(d);(p/'tb.sv').write_text(TB)
    subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.PERIOD={period}','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_sdram_burst.sv')],check=True)
    r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=20)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS period=',r.stdout)

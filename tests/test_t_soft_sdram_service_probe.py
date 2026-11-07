"""Every service output reaches the delayed signature, including the final group."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TB=r'''
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0;wire signature;
reg[367:0] observation=0;reg[1:0] history=0;reg expected=0;
integer lane,cycle=0;
t_soft_sdram_service_probe dut(clk,resetn,1'b0,1'b0,signature);
always @(posedge clk)begin
 if(!resetn)begin history=0;expected=0;end
 else begin
  expected=expected^history[1];history={history[0],^observation};
 end
 #1;if(signature!==expected)$fatal(1,"signature delay/coverage cycle %0d",cycle);
 cycle=cycle+1;
end
initial begin
 force dut.observed=observation;
 repeat(3)@(negedge clk);resetn=1;
 for(lane=0;lane<368;lane=lane+1)begin
  observation=0;observation[lane]=1;
  @(negedge clk);observation=0;
  repeat(4)@(negedge clk);
 end
 observation={368{1'b1}};@(negedge clk);observation=0;
 repeat(5)@(negedge clk);
 $display("PASS all 368 lanes reach the three-stage signature");$finish;
end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ObservationTest(unittest.TestCase):
 def test_all_integrated_output_lanes(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(TB)
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'experiments/t_soft_sdram_service_probe.sv'),
    *(str(ROOT/'rtl'/f) for f in ('sdf_delay_cache.sv','sdram_client_arbiter.sv','dual_sdram_burst.sv','sdf_sdram_service.sv','t_soft_reader.sv','t_soft_sdram_service.sv'))],check=True)
   r=subprocess.run(['vvp',str(p/'sim')],text=True,capture_output=True,timeout=20)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS all 368 lanes',r.stdout)

"""Reject background accesses to FFT bank and oversized logical FFT frames."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BENCH=r'''`timescale 1ns/1ps
module tb;
reg clk=0,resetn=0,tv=0,sv=0,start=0;always #5 clk=~clk;
wire tr,sr,mfault,ffault;reg[20:0] base=0;
dual_fft_memory_clients #(.INIT_CYCLES(32)) dut(
 .core_clk(clk),.mem_clk(clk),.resetn(resetn),.start(start),.mode_log(4'd13),
 .input_base(base),.middle_base(21'd8192),.output_base(21'd16384),.fft_fault(ffault),
 .other_valid(tv),.other_ready(tr),.other_write(1'b1),.other_address(21'd0),.other_data(256'd0),.other_dqm(32'd0),.other_rsp_ready(1'b1),
 .s_valid(sv),.s_ready(sr),.s_write(1'b1),.s_address(21'd0),.s_data(256'd0),.s_dqm(32'd0),.s_rsp_ready(1'b1),
 .memory_fault(mfault),.dq_in(32'd0));
initial begin
 repeat(3)@(negedge clk);resetn=1;tv=1;
 @(posedge clk);#1;if(!mfault||tr)$fatal(1,"T bank violation not rejected");
 @(negedge clk);resetn=0;tv=0;
 repeat(3)@(negedge clk);resetn=1;sv=1;
 @(posedge clk);#1;if(!mfault||sr)$fatal(1,"S bank violation not rejected");
 @(negedge clk);resetn=0;sv=0;
 repeat(3)@(negedge clk);resetn=1;base=21'd520192;start=1;
 @(posedge clk);#1;if(!ffault)$fatal(1,"oversized FFT frame not rejected");
 $display("PASS partitions");$finish;
end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class Partition(unittest.TestCase):
    def test_rejected_addresses(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/'tb.sv').write_text(BENCH)
            files=list((ROOT/'rtl').glob('dual_fft_*.sv'))+list((ROOT/'rtl').glob('dual_burst_*.sv'))+[ROOT/'rtl/dual_sdram_burst.sv']
            subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),*map(str,files)],check=True)
            r=subprocess.run(['vvp',str(p/'sim')],cwd=ROOT,capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn('PASS',r.stdout)

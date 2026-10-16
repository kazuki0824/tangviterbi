"""Experimental RTL smoke tests, deliberately not full FFT correctness."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TB=r"""
module tb;
 reg clk=0, resetn=0, iv=0, rd=1;
 reg [31:0] din=0;
 wire ir,ov,orx,ore,owe;wire [31:0] dout,wdata;wire [1:0] ra,wa;
 reg [31:0] ext_q=0,ext_mem[0:3];
 reg [31:0] accepted=0,produced=0;integer i;
 research_sdf_stage #(.SHIFT(2),.EXTERNAL(1)) dut
 ( .clk(clk),.resetn(resetn),.in_valid(iv),.in_ready(ir),.in_data(din),
 .out_valid(ov),.out_ready(rd),.out_data(dout),
 .external_ready(1'b1),.external_read_enable(ore),
 .external_read_addr(ra),.external_read_data(ext_q),
 .external_write_enable(owe),.external_write_addr(wa),
 .external_write_data(wdata),.overflow(orx));
 always #5 clk=~clk;
 always @(posedge clk) begin
    if(ore)ext_q<=ext_mem[ra];
    if(owe)ext_mem[wa]<=wdata;
    if(iv&&ir)accepted<=accepted+1;
    if(ov&&rd) begin
      if(dout!==32'd0)$fatal(1,"nonzero output");
      produced<=produced+1;
    end
 end
 initial begin
 for(i=0;i<4;i=i+1)ext_mem[i]=0;
 repeat(3)@(negedge clk);resetn=1;
 for(i=0;i<16;i=i+1)begin
   @(negedge clk);iv=1;din=0;
   while(!ir)@(negedge clk);
   @(negedge clk);iv=0;
 end
 repeat(8)@(negedge clk);
 if(accepted!==16 || produced!==12)$fatal(1,"counts a=%d p=%d",accepted,produced);
 $display("PASS stage zero-vector handshakes: %d/%d",accepted,produced);
 $finish;
 end
endmodule
"""
@unittest.skipUnless(shutil.which("iverilog") and shutil.which("vvp"),"Icarus required")
class TestResearchStage(unittest.TestCase):
 def test_external_zero_stream(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)
   (p/"tb.sv").write_text(TB)
   subprocess.run(["iverilog","-g2012","-s","tb","-o",str(p/"sim"),str(p/"tb.sv"),str(ROOT/"rtl/research_sdf_stage.sv"),str(ROOT/"rtl/research_sdf_twiddle.sv")],check=True,cwd=ROOT,timeout=30)
   r=subprocess.run(["vvp",str(p/"sim")],capture_output=True,text=True,cwd=ROOT,timeout=30)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   self.assertIn("PASS stage",r.stdout)

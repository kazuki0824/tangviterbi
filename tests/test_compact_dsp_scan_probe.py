"""Probe scan semantics with a restricted ALU54D model derived from UG287.
Not a vendor primitive simulation or physical DSP validation.
"""
import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MODEL=r'''
module ALU54D #(parameter AREG=0,BREG=0,ASIGN_REG=0,BSIGN_REG=0,
 ACCLOAD_REG=0,OUT_REG=1,B_ADD_SUB=0,C_ADD_SUB=0,ALUD_MODE=2,
 ALU_RESET_MODE="SYNC")(
 input[53:0] A,B,input[54:0]CASI,input ASIGN,BSIGN,ACCLOAD,CLK,CE,RESET,
 output reg[53:0]DOUT,output[54:0]CASO);
 initial if(AREG||BREG||ASIGN_REG||BSIGN_REG||ACCLOAD_REG||!OUT_REG||B_ADD_SUB||C_ADD_SUB||ALUD_MODE!=2||ALU_RESET_MODE!="SYNC")$fatal(1,"unsupported model");
 always @(posedge CLK)if(RESET)DOUT<=0;else if(CE)DOUT<=A+B+CASI;
 assign CASO={1'b0,DOUT};
endmodule
'''
class ProbeTest(unittest.TestCase):
 def test_all_bits_hold_and_reset(self):
  # Stub core does not validate the receiver. Hierarchical scan comparison
  # exercises the actual new probe, including boundaries between all 21 DSPs.
  header=(ROOT/'experiments/shared_receiver_fft_tile.sv').read_text().split('module shared_receiver_fft_tile(',1)[1].split(');',1)[0]
  stub='module shared_receiver_fft_tile('+header+'); endmodule\n'
  tb=r'''
module tb;
reg clk=0,resetn=0,en=0,si=0;wire signature;
reg[1296:0]expected=0;reg[31:0]rng=32'h173ae981;integer i;
always #5 clk=~clk;
shared_receiver_fft_tile_probe dut(clk,resetn,en,si,signature);
always @(posedge clk)if(!resetn)expected<=0;else if(en)expected<={expected[1295:0],si};
initial begin
 for(i=0;i<7000;i=i+1)begin
  @(negedge clk);rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  resetn=i>2&&i!=5300;en=i<3300?1:rng[1];si=rng[0];
  @(posedge clk);#1;if(dut.scan_state!==expected)$fatal(1,"scan mismatch cycle %d",i);
 end
 @(negedge clk);en=0;resetn=0;@(posedge clk);#1;
 if(dut.stimulus!==0)$fatal(1,"disabled reset mismatch");
 $display("PASS 7000 scan/hold/reset cycles, all 1297 bits");$finish;
end
endmodule
'''
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);(p/'tb.sv').write_text(MODEL+stub+tb)
   r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'experiments/shared_receiver_fft_tile_compact_dsp_probe.sv')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=120)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(r.stdout)

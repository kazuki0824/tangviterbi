"""Verify alternating-address observation capture; DSP uses the restricted model."""
import subprocess,tempfile,unittest
from pathlib import Path
from test_dsp_scan_probe import MODEL,ROOT
class ObservationTest(unittest.TestCase):
 def test_all_output_bits_and_reset(self):
  header=(ROOT/'experiments/shared_receiver_fft_tile.sv').read_text().split('module shared_receiver_fft_tile(',1)[1].split(');',1)[0]
  stub='module shared_receiver_fft_tile('+header+'); endmodule\n'
  tb=r'''
module tb;
reg clk=0,resetn=0,en=0,si=0;wire signature;
reg[383:0]drive=0,previous=0;reg valid=0;integer i;
always #5 clk=~clk;
shared_receiver_fft_tile_probe dut(clk,resetn,en,si,signature);
initial begin
 force dut.observed=drive;
 for(i=0;i<800;i=i+1)begin
  @(negedge clk);resetn=i>3&&i!=403;
  drive=384'd1<<(i%384);
  @(posedge clk);#1;
  if(resetn&&valid&&dut.observed_capture!==previous)$fatal(1,"capture mismatch %d",i);
  if(resetn&&dut.observe_fill==3&&(^dut.digest_chunks===1'bx))$fatal(1,"unknown checksum %d",i);
  if(!resetn&&signature!==0)$fatal(1,"reset signature");
  previous=drive;valid=resetn;
 end
 $display("PASS all 384 observation bits, alternating addresses and reset");$finish;
end
endmodule
'''
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);(p/'tb.sv').write_text(MODEL+stub+tb)
   r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'experiments/shared_receiver_fft_tile_compact_bram_probe.sv')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=30)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(r.stdout)

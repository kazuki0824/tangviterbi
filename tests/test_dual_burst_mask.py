"""Mask bundled-data CDC with independent clocks and request/response stalls."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BENCH=r'''`timescale 1ns/1ps
module tb;
reg ac=0,bc=0,resetn=0;
always #3.1 ac=~ac;
always #3.7 bc=~bc;
integer sent=0,received=0,accepted=0,cycles=0,bcounter=0,delay=0;
wire av,ar,arv,bv,bw,brr;
assign av=sent<512;
wire[20:0] ba;wire[255:0] bd,ard;wire[31:0] bm;
wire br=delay==0&&!brv&&(bcounter%7)!=0;
wire arr=(cycles%29)>12;
reg brv=0;reg[255:0] brd=0;
wire[31:0] am=32'h12345678^(32'h9e3779b9*sent);
dual_burst_cdc dut(ac,bc,resetn,av,ar,sent[0],21'(sent*8),{8{32'(sent)}},arv,arr,ard,
 bv,br,bw,ba,bd,brv,brr,brd,am,bm);
reg holding=0;reg[309:0] held;
always @(posedge bc)if(resetn)begin
 bcounter=bcounter+1;
 if(holding && {bw,ba,bd,bm}!==held)$fatal(1,"CDC request or mask unstable");
 holding=bv&&!br;held={bw,ba,bd,bm};
 if(bv&&br)begin
  if(bm!==(32'h12345678^(32'h9e3779b9*accepted)) || ba!==21'(accepted*8) || bd!=={8{32'(accepted)}} || bw!==accepted[0])$fatal(1,"CDC metadata mismatch");
  brd<={8{32'(accepted)^bm}};accepted=accepted+1;delay=5;
 end else if(delay>0)begin delay=delay-1;if(delay==0)brv<=1;end
 if(brv&&brr)brv<=0;
end
always @(posedge ac)if(resetn)begin
 cycles=cycles+1;
 if(av&&ar)sent<=sent+1;
 if(arv&&arr)begin
  if(ard!=={8{32'(received)^(32'h12345678^(32'h9e3779b9*received))}})$fatal(1,"CDC response mismatch");
  received=received+1;
  if(received==512)begin $display("PASS masks=512");$finish;end
 end
 if(cycles>100000)$fatal(1,"timeout");
end
initial begin #30;resetn=1;end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class MaskCDC(unittest.TestCase):
    def test_masks_survive_stalls(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/'tb.sv').write_text(BENCH)
            subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_burst_cdc.sv')],check=True)
            r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn('PASS masks=512',r.stdout)

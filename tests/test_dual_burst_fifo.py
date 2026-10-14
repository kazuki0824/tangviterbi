"""Bounded packed request FIFO: fill, wrap, simultaneous enqueue/dequeue, stalls."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BENCH=r'''`timescale 1ns/1ps
module tb;
parameter DEPTH=256;
reg clk=0,resetn=0;always #5 clk=~clk;
integer sent=0,received=0,cycles=0,full=0;
wire ir,ov,ow;wire[20:0] oa;wire[255:0] od;wire[31:0] om;wire[15:0] level;
wire iv=sent<4096&&(cycles%11)!=4;
wire ready=cycles>DEPTH*4 && (cycles%23)>7;
dual_burst_fifo #(.DEPTH(DEPTH)) dut(clk,resetn,iv,ir,sent[0],21'(sent*8),{8{32'(sent)}},32'hffffffff^32'(sent),ov,ready,ow,oa,od,om,level);
reg held_valid=0;reg[309:0] held;
always @(posedge clk)if(resetn)begin
 cycles=cycles+1;
 if(level>DEPTH+2)$fatal(1,"capacity violated");
 if(iv&&!ir)full=full+1;
 if(held_valid&&(!ov||{ow,oa,od,om}!==held))$fatal(1,"output changed under stall");
 held_valid=ov&&!ready;held={ow,oa,od,om};
 if(iv&&ir)sent<=sent+1;
 if(ov&&ready)begin
  if(ow!==received[0] || oa!==21'(received*8) || od!=={8{32'(received)}} || om!==(32'hffffffff^32'(received)))$fatal(1,"descriptor mismatch %0d",received);
  received=received+1;
  if(received==4096)begin if(full==0)$fatal(1,"no full coverage");$display("PASS depth=%0d",DEPTH);$finish;end
 end
 if(cycles>100000)$fatal(1,"timeout");
end
initial begin #30;resetn=1;end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class PackedFIFO(unittest.TestCase):
    def test_full_wrap_stalls(self):
        for depth in (4,256):
            with self.subTest(depth=depth),tempfile.TemporaryDirectory() as temp:
                p=Path(temp);(p/'tb.sv').write_text(BENCH)
                subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.DEPTH={depth}','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_burst_fifo.sv')],check=True)
                r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=30)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                self.assertIn('PASS',r.stdout)

"""Whole-frame RTL-vs-independent bit-exact integer DIF FFT comparison.

The RTL currently needs a *testbench-supplied* N-1 zero tail to drain the
streaming pipeline, plus reset before each frame. This is not a production
frame adapter or an operational SDRAM timing model.
"""
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from experiments.research_sdf_oracle import (
    bit_reverse, decode_word, encode_word, load_quarter, reference_fft
)

ROOT=Path(__file__).resolve().parents[1]
TB=r"""
module tb;
parameter LOGN=11;
localparam N=(1<<LOGN), TOTAL=2*N-1, D=N/2;
reg clk=0; always #5 clk=~clk;
reg resetn=0, in_valid=0, out_ready=1, external_ready=1;
reg [31:0] in_data=0;
wire in_ready,out_valid,ext_re,ext_we,overflow,end_frame;
wire [31:0] out_data,ext_wdata;
wire [LOGN-1:0] out_bin;
wire [LOGN-2:0] ext_ra,ext_wa;
reg [31:0] ext_q=0, ext_mem[0:D-1], stimulus[0:N-1];
integer sent=0,received=0,cycles=0,j;
research_sdf_fft #(.LOGN(LOGN)) dut(
 .clk(clk),.resetn(resetn),.in_valid(in_valid),.in_ready(in_ready),
 .in_data(in_data),.out_valid(out_valid),.out_ready(out_ready),
 .out_data(out_data),.out_bin(out_bin),.out_frame_end(end_frame),
 .external_ready(external_ready),.external_read_enable(ext_re),
 .external_read_addr(ext_ra),.external_read_data(ext_q),
 .external_write_enable(ext_we),.external_write_addr(ext_wa),
 .external_write_data(ext_wdata),.overflow(overflow));
always @(posedge clk) begin
 if(ext_re) ext_q<=ext_mem[ext_ra];
 if(ext_we) ext_mem[ext_wa]<=ext_wdata;
 if(resetn) begin
  cycles<=cycles+1;
  if(in_valid&&in_ready)sent<=sent+1;
  if(out_valid&&out_ready)begin
   $display("OUT %0d %0d %08h",received,out_bin,out_data);
   if(received==N-1 && !end_frame)$fatal(1,"missing final frame marker");
   if(received!=N-1 && end_frame)$fatal(1,"early frame marker");
   received<=received+1;
  end
  if(cycles>300000)$fatal(1,"timeout sent=%0d received=%0d",sent,received);
 end
end
always @(negedge clk)begin
 if(resetn)begin
  in_valid=(sent<TOTAL);
  in_data=sent<N ? stimulus[sent] : 0;
  external_ready=((cycles%11)!=3 && (cycles%11)!=4);
  out_ready=((cycles%17)!=7 && (cycles%17)!=8 && (cycles%17)!=9);
 end
end
initial begin
 $readmemh("input.hex",stimulus);
 for(j=0;j<D;j=j+1) ext_mem[j]=32'd0;
 repeat(4)@(negedge clk);
 resetn=1;
 wait(received==N);
 @(negedge clk);
 if(sent!=TOTAL)$fatal(1,"wrong drained input count %0d",sent);
 if(overflow)$fatal(1,"unexpected clipping");
 $display("PASS N=%0d accepted=%0d output=%0d cycles=%0d",N,sent,received,cycles);
 $finish;
end
endmodule
"""

@unittest.skipUnless(shutil.which("iverilog") and shutil.which("vvp"),
                     "Icarus Verilog required")
class WholeFrameRTL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.coeffs=load_quarter()

    def run_frame(self,logn,case):
        n=1<<logn
        rng=random.Random(n*77+len(case))
        if case=="impulse":
            words=[0]*n
            words[0]=encode_word(16384,0)
        elif case=="tone":
            # Phase rotates among real/imag quadrants without double arithmetic.
            vals=((12000,0),(0,12000),(-12000,0),(0,-12000))
            words=[encode_word(*vals[(i*7)%4]) for i in range(n)]
        else:
            words=[encode_word(rng.randrange(-2048,2049),
                               rng.randrange(-2048,2049)) for _ in range(n)]
        ref=reference_fft(words,self.coeffs)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/"tb.sv").write_text(TB)
            (p/"input.hex").write_text("".join(f"{w:08x}\n" for w in words))
            cmd=["iverilog","-g2012","-s","tb",f"-Ptb.LOGN={logn}",
                 "-o",str(p/"run"),str(p/"tb.sv"),
                 str(ROOT/"rtl/research_sdf_fft.sv"),
                 str(ROOT/"rtl/research_sdf_stage.sv"),
                 str(ROOT/"rtl/research_sdf_twiddle.sv")]
            subprocess.run(cmd,cwd=ROOT,check=True,capture_output=True,text=True,timeout=60)
            result=subprocess.run(["vvp",str(p/"run")],cwd=ROOT,
                                  capture_output=True,text=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stderr+"\n"+result.stdout[-3000:])
        rows=[l.split() for l in result.stdout.splitlines() if l.startswith("OUT ")]
        self.assertEqual(len(rows),n)
        for seq,line in enumerate(rows):
            _,seen_seq,seen_bin,hex_word=line
            self.assertEqual(int(seen_seq),seq)
            self.assertEqual(int(seen_bin),bit_reverse(seq,logn))
            self.assertEqual(int(hex_word,16),ref[seq],
                f"mode={logn}, case={case}, seq={seq}, bin={seen_bin}, "
                f"got={decode_word(int(hex_word,16))}, "
                f"ref={decode_word(ref[seq])}")
        self.assertIn(f"PASS N={n}",result.stdout)

    def test_mode1_nonzero(self): self.run_frame(11,"random")
    def test_mode2_nonzero(self): self.run_frame(12,"random")
    def test_mode3_nonzero(self): self.run_frame(13,"random")
    def test_impulse(self): self.run_frame(11,"impulse")

if __name__=="__main__":
    unittest.main()

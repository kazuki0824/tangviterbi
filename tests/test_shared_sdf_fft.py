"""Continuous frames: all bins vs independent DIF and floating DFT oracles.

Four real frames are sent; the first three complete outputs are checked. The
fourth nonzero frame advances the pipeline, with no dummy zeros/frame reset.
External memory in this test is explicitly an ideal reserved synchronous port.
"""
import importlib.util
import math
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "reports/pr7-fft-archive"
SPEC = importlib.util.spec_from_file_location(
    "archived_dif_oracle", ARCHIVE / "experiments/research_sdf_oracle.py"
)
ORACLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ORACLE)

TB = r"""
module tb;
parameter MODE=2, EXTERNAL=1, STALL=0, PREVIOUS_MODE=-1;
localparam N=1<<(11+MODE), FRAMES=4, CHECK=3*N;
reg clk=0; always #5 clk=~clk;
reg resetn=0, in_valid=0, out_ready=1, external_ready=1;
reg [31:0] in_data=0;
reg [1:0] selected_mode=PREVIOUS_MODE>=0 ? PREVIOUS_MODE : MODE;
reg checking=PREVIOUS_MODE<0;
wire in_ready,out_valid,re,we,overflow,frame_end;
wire [31:0] out_data,wd;
wire [11:0] ra,wa;
wire [12:0] bin;
reg [31:0] ext_q,mem[0:4095],source[0:FRAMES*N-1];
reg [8*1024-1:0] path;
integer sent=0,received=0,cycles=0,last_input=-1,max_input_gap=0;
integer first_input=-1,last_output=-1,max_output_gap=0,frame_cycle[0:2];
reg held=0;
reg [31:0] held_data;
reg [12:0] held_bin;
shared_sdf_fft #(.EXTERNAL_FIRST(EXTERNAL)) dut(
 .clk(clk),.resetn(resetn),.mode(selected_mode),
 .in_valid(in_valid),.in_ready(in_ready),.in_data(in_data),
 .out_valid(out_valid),.out_ready(out_ready),.out_data(out_data),
 .out_bin(bin),.out_frame_end(frame_end),.external_ready(external_ready),
 .external_read_enable(re),.external_read_addr(ra),.external_read_data(ext_q),
 .external_write_enable(we),.external_write_addr(wa),.external_write_data(wd),
 .overflow(overflow));
always @(posedge clk) begin
 if(re) ext_q<=mem[ra];
 if(we) mem[wa]<=wd;
 if(resetn) begin
  cycles<=cycles+1;
  if(in_valid&&in_ready) begin
   sent<=sent+1;
   if(last_input>=0 && cycles-last_input>max_input_gap)max_input_gap<=cycles-last_input;
   if(first_input<0)first_input<=cycles;
   last_input<=cycles;
  end
  if(held && (!out_valid || out_data!==held_data || bin!==held_bin))
    $fatal(1,"output changed under backpressure");
  held<=out_valid&&!out_ready;held_data<=out_data;held_bin<=bin;
  if(out_valid&&out_ready) begin
   if((^out_data)===1'bx)$fatal(1,"unknown output");
   if(checking && frame_end !== ((received%N)==N-1))$fatal(1,"frame marker");
   if(checking)$display("OUT %0d %0d %08h",received,bin,out_data);
   received<=received+1;
   if(last_output>=0 && cycles-last_output>max_output_gap)max_output_gap<=cycles-last_output;
   last_output<=cycles;
   if(frame_end && received<CHECK)frame_cycle[received/N]<=cycles;
  end
  if(cycles>1200000)$fatal(1,"timeout sent=%0d received=%0d",sent,received);
 end
end
always @(negedge clk) if(resetn) begin
 in_valid=sent<FRAMES*N;
 in_data=sent<FRAMES*N ? source[sent] : 32'hdeadbeef;
 // Long sink stalls and unavailable external reservations.
 // Once offered a sample, its contents stay stable until accepted.
 out_ready=!STALL || (cycles%181<111);
 external_ready=!STALL || (cycles%97<77);
end
initial begin
 if(!$value$plusargs("INPUT_HEX=%s",path))$fatal(1,"input path");
 $readmemh(path,source);
 repeat(5)@(negedge clk);resetn=1;
 if(PREVIOUS_MODE>=0) begin
  repeat(60000)@(negedge clk);
  resetn=0;selected_mode=MODE;in_valid=0;
  // Keep every RAM word dirty while changing modes. Only state is reset.
  repeat(5)@(negedge clk);
  sent=0;received=0;cycles=0;last_input=-1;first_input=-1;
  last_output=-1;max_input_gap=0;max_output_gap=0;held=0;
  checking=1;resetn=1;
 end
 wait(received==CHECK);@(negedge clk);
 if(!STALL && (max_input_gap!=13 || max_output_gap!=13))
   $fatal(1,"continuous rate in=%0d out=%0d",max_input_gap,max_output_gap);
 $display("PASS sent=%0d checked=%0d cycles=%0d frame_cycles=%0d,%0d,%0d input_gap=%0d output_gap=%0d clipped=%0d",
 sent,received,cycles,frame_cycle[0],frame_cycle[1],frame_cycle[2],max_input_gap,max_output_gap,overflow);
 $finish;
end
endmodule
"""


def vectors(n, case):
    rng = random.Random(n * 17 + len(case))
    result = []
    for frame in range(4):
        if case == "extreme":
            values = [(rng.choice((-32768, 32767)), rng.choice((-32768, 32767)))
                      for _ in range(n)]
        elif case == "tone":
            values = [(round(12000 * math.cos(2 * math.pi * (31 + frame) * j / n)),
                       round(12000 * math.sin(2 * math.pi * (31 + frame) * j / n)))
                      for j in range(n)]
        else:
            values = [(rng.randrange(-8192, 8193), rng.randrange(-8192, 8193))
                      for _ in range(n)]
        result.extend(ORACLE.encode_word(*x) for x in values)
    return result


@unittest.skipUnless(shutil.which("iverilog") and shutil.which("vvp"), "Icarus required")
class SharedSDFTests(unittest.TestCase):
    def run_case(self, mode, external=1, stall=0, case="random", previous_mode=-1):
        n = 1 << (11 + mode)
        words = vectors(n, case)
        table = ORACLE.load_quarter()
        expected = sum((ORACLE.reference_fft(words[f*n:(f+1)*n], table)
                        for f in range(3)), [])
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "tb.sv").write_text(TB)
            (p / "input.hex").write_text("".join(f"{w:08x}\n" for w in words))
            compile_result = subprocess.run([
                "iverilog", "-g2012", "-s", "tb", f"-Ptb.MODE={mode}",
                f"-Ptb.EXTERNAL={external}", f"-Ptb.STALL={stall}",
                f"-Ptb.PREVIOUS_MODE={previous_mode}",
                "-o", str(p / "run"), str(p / "tb.sv"),
                str(ROOT / "rtl/shared_sdf_fft.sv"),
                str(ARCHIVE / "rtl/research_sdf_twiddle.sv"),
            ], cwd=ARCHIVE, capture_output=True, text=True, timeout=60)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run = subprocess.run(["vvp", str(p / "run"), f"+INPUT_HEX={p/'input.hex'}"],
                                 cwd=ARCHIVE, capture_output=True, text=True, timeout=180)
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout[-2000:])
        rows = [line.split() for line in run.stdout.splitlines() if line.startswith("OUT ")]
        self.assertEqual(len(rows), 3*n)
        for seq, row in enumerate(rows):
            self.assertEqual(int(row[1]), seq)
            self.assertEqual(int(row[2]), ORACLE.bit_reverse(seq % n, 11+mode))
            self.assertEqual(int(row[3], 16), expected[seq], f"mode {mode}, output {seq}")
        print(f"MODE={mode+1} external={external} stall={stall} case={case} " +
              next(line for line in run.stdout.splitlines() if line.startswith("PASS ")))

    def test_mode1_continuous(self): self.run_case(0)
    def test_mode2_continuous(self): self.run_case(1)
    def test_mode3_continuous(self): self.run_case(2)
    def test_mode3_backpressure(self): self.run_case(2, stall=1)
    def test_mode1_resident(self): self.run_case(0, external=0)
    def test_mode3_resident(self): self.run_case(2, external=0)
    def test_full_scale_saturation(self): self.run_case(0, case="extreme")
    def test_nonzero_tones(self): self.run_case(1, case="tone")
    def test_reset_mode1_to_mode3_with_dirty_ram(self): self.run_case(2, previous_mode=0)
    def test_reset_mode3_to_mode1_with_dirty_ram(self): self.run_case(0, previous_mode=2)

    def test_independent_numpy_accuracy(self):
        import numpy as np
        for mode in range(3):
            n = 1 << (11 + mode)
            words = vectors(n, "random")[:n]
            fixed = ORACLE.reference_fft(words, ORACLE.load_quarter())
            decoded = [ORACLE.decode_word(w) for w in words]
            floating = np.fft.fft([complex(*x) for x in decoded])/n
            error = max(abs(complex(*ORACLE.decode_word(w)) -
                            floating[ORACLE.bit_reverse(j, 11+mode)])
                        for j, w in enumerate(fixed))
            self.assertLess(error, 12, f"mode {mode}, Q15 error {error}")


if __name__ == "__main__":
    unittest.main()

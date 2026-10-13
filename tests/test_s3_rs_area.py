from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
from s3_rs_area import source


class SharedMultiplierTests(unittest.TestCase):
    def test_cycle_equivalence_and_operand_exclusion(self):
        """Check the sharing schedule against the dual Boolean-multiplier RTL."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dual = root / "dual.sv"
            candidate = root / "shared.sv"
            bench = root / "bench.sv"
            dual.write_text(source())
            shared = source(True)
            # Reuse identical GF and block-RAM modules from the dual source.
            shared = shared[shared.index("module rs204_188_compact"):]
            candidate.write_text(shared.replace("module rs204_188_compact", "module rs_shared", 1))
            bench.write_text(r'''
module share_tb;
  reg clk=0, resetn=0, in_valid=0;
  reg [7:0] in_byte=0;
  wire ready_a, ready_b, valid_a, valid_b, fail_a, fail_b;
  wire [7:0] byte_a, byte_b;
  reg [31:0] rng=32'h189a37f5;
  integer n, accepted=0, outputs=0;
  rs204_188_compact a(clk,resetn,in_valid,ready_a,in_byte,valid_a,byte_a,fail_a);
  rs_shared b(clk,resetn,in_valid,ready_b,in_byte,valid_b,byte_b,fail_b);
  always #5 clk=~clk;
  initial begin
    for (n=0; n<220000; n=n+1) begin
      @(negedge clk);
      if (resetn) begin
        if ({ready_a,valid_a,fail_a} !== {ready_b,valid_b,fail_b})
          $fatal(1,"handshake/status mismatch at cycle %0d", n);
        if (valid_a && byte_a !== byte_b) $fatal(1,"output mismatch at %0d",n);
        if (((a.coefficient_next_a | a.coefficient_next_b) != 0) &&
            ((a.feedback_next_a | a.feedback_next_b) != 0))
          $fatal(1,"simultaneous operand groups at %0d",n);
        if (valid_a) outputs=outputs+1;
        if (ready_a && in_valid) accepted=accepted+1;
      end
      rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
      resetn=(n>3 && n!=76543 && n!=142017);
      in_valid=|rng[3:1];
      in_byte=(n<30000) ? 0 : rng[15:8];
    end
    if (outputs<2000 || accepted<4000) $fatal(1,"insufficient stream coverage");
    $display("PASS cycle equivalence: %0d input bytes, %0d output bytes, stalls and resets",accepted,outputs);
    $finish;
  end
endmodule
''')
            program = root / "sim"
            subprocess.run(["iverilog", "-g2012", "-s", "share_tb", "-o", str(program),
                            str(dual), str(candidate), str(bench)], check=True)
            subprocess.run(["vvp", str(program)], check=True, timeout=120)


if __name__ == "__main__":
    unittest.main()

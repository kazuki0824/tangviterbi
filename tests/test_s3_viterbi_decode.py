"""External convolutional encoder oracle; independent of decoder internals."""
import importlib.util
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("trace", ROOT / "experiments/s3_viterbi_traceback.py")
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)


def stimulus(bits, noise=False):
    state = 0
    result = []
    for i, bit in enumerate(bits):
        state = ((state << 1) | bit) & 127
        pair = [(state & g).bit_count() & 1 for g in (0o171, 0o133)]
        soft = [230 if b else 25 for b in pair]
        if noise and i % 97 == 31:
            soft[i % 2] = 255-soft[i % 2]
        result.append((soft[0] << 8) | soft[1])
    return result


def run(rtl, module, bits, noise=False, stalls=False):
    with tempfile.TemporaryDirectory() as out:
        out = Path(out)
        (out / "input.hex").write_text("".join(f"{v:04x}\n" for v in stimulus(bits, noise)))
        (out / "dut.sv").write_text(rtl)
        (out / "tb.sv").write_text(f'''module tb;
reg clk=0; always #5 clk=~clk;
reg resetn=0, valid=0; wire ready, ov; wire ob;
reg [7:0] s0=0,s1=0; reg [15:0] words[0:{len(bits)-1}];
integer n=0, cycles=0, f;
{module} dut(clk,resetn,valid,ready,s0,s1,ov,ob);
initial begin $readmemh("input.hex",words); f=$fopen("output.txt","w");
repeat(4) @(negedge clk); resetn=1;
while(n < {len(bits)}) begin
@(negedge clk); valid=0;
if(ready && (!{int(stalls)} || cycles%11 != 3)) begin
s0=words[n][15:8];s1=words[n][7:0]; valid=1;n=n+1;end
cycles=cycles+1;
end
@(negedge clk);valid=0;repeat(400) @(negedge clk);
$fclose(f);$finish;end
always @(posedge clk) begin #1;if(ov) $fdisplay(f,"%0d",ob);end
endmodule''')
        subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(out / "sim"),
                        str(out / "dut.sv"), str(out / "tb.sv")], check=True, capture_output=True)
        subprocess.run(["vvp", str(out / "sim")], cwd=out, check=True, capture_output=True, timeout=90)
        return [int(v) for v in (out / "output.txt").read_text().split()]


@unittest.skipUnless(shutil.which("iverilog"), "Icarus required")
class DecodeTest(unittest.TestCase):
    def test_independent_encoder(self):
        rng = random.Random(0x171133)
        reports = []
        for name, bits, noise, stalls in (
            ("zeros", [0]*2048, False, False),
            ("ones", [1]*2048, False, False),
            ("random", [rng.randrange(2) for _ in range(4096)], False, False),
            ("isolated_errors_stalls", [rng.randrange(2) for _ in range(4096)], True, True),
            ("metric_renormalization", [rng.randrange(2) for _ in range(16384)], True, False),
        ):
            with self.subTest(name=name):
                result = run(trace.generate(), "s3_viterbi_traceback", bits, noise, stalls)
                errors = sum(a != b for a,b in zip(result,bits))
                reports.append(dict(name=name, outputs=len(result), errors=errors))
                self.assertGreater(len(result), len(bits)-300)
                self.assertEqual(errors,0, reports[-1])
        dest=ROOT / "build/s3-viterbi";dest.mkdir(parents=True,exist_ok=True)
        (dest / "decode.json").write_text(json.dumps(reports,indent=2)+"\n")


if __name__ == "__main__":
    unittest.main()

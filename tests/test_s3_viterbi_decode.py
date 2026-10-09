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


def stimulus(bits, noise=False, initial_state=0):
    state = initial_state
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
    def test_unknown_state_and_reset_aborts_inflight_traceback(self):
        rng=random.Random(0xC1EA2)
        epochs=[[rng.randrange(2) for _ in range(512+73*i)] for i in range(8)]
        words=[w for i,b in enumerate(epochs) for w in stimulus(b,initial_state=(7+9*i)%64)]
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory)
            (d/'dut.sv').write_text(trace.generate('modulo13'))
            (d/'input.hex').write_text(''.join(f'{v:04x}\n' for v in words))
            counts='\n'.join(f'lengths[{i}]={len(b)};' for i,b in enumerate(epochs))
            (d/'tb.sv').write_text(f'''module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,valid=0;reg [7:0]a=0,b=0;wire ready,ov,ob;
integer lengths[0:7];reg[15:0]words[0:{len(words)-1}];
integer e=0,n,at=0,tick=0,f;
s3_viterbi_traceback dut(clk,resetn,valid,ready,a,b,ov,ob);
initial begin {counts}
f=$fopen("epochs.txt","w");$readmemh("input.hex",words);
for(e=0;e<8;e=e+1)begin
resetn=0;valid=0;repeat(3)@(negedge clk);resetn=1;n=0;
while(n<lengths[e])begin
@(negedge clk);valid=0;
// Long stalls let traceback finish while input is idle.
if(ready && (tick%503<410))begin
a=words[at][15:8];b=words[at][7:0];valid=1;n=n+1;at=at+1;end
tick=tick+1;end
@(negedge clk);valid=0;repeat(e%3)@(negedge clk);
// Abort with outstanding output; no tail from epoch e may leak to e+1.
resetn=0;
end
$fclose(f);$finish;end
always @(posedge clk)begin #1;
if(!resetn && ov)$fatal(1,"output remained valid during reset");
if(resetn && ov)$fdisplay(f,"%0d %0d",e,ob);end
endmodule''')
            subprocess.run(['iverilog','-g2012','-s','tb','-o',str(d/'sim'),str(d/'dut.sv'),str(d/'tb.sv')],check=True,capture_output=True)
            subprocess.run(['vvp',str(d/'sim')],cwd=d,check=True,capture_output=True,timeout=90)
            actual=[[] for _ in epochs]
            for line in (d/'epochs.txt').read_text().splitlines():
                e,bit=map(int,line.split());actual[e].append(bit)
        for e,(got,want) in enumerate(zip(actual,epochs)):
            self.assertGreater(len(got),128,e)
            self.assertEqual(got[64:],want[64:len(got)],e)
        dest=ROOT/'build/s3-viterbi';dest.mkdir(parents=True,exist_ok=True)
        (dest/'reset-oracle.json').write_text(json.dumps({'epochs':len(epochs),'unknown_initial_states':True,
            'inflight_reset':True,'long_input_stalls':True,'discard_first_bits_each_epoch':64,
            'checked_outputs':[len(a)-64 for a in actual],'errors':0},indent=2)+'\n')

    def test_independent_encoder(self):
        for mode in ("normalized14","modulo13"):
            with self.subTest(arithmetic=mode): self.check_mode(mode)

    def check_mode(self,mode):
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
                result = run(trace.generate(mode), "s3_viterbi_traceback", bits, noise, stalls)
                errors = sum(a != b for a,b in zip(result,bits))
                reports.append(dict(name=name, outputs=len(result), errors=errors))
                self.assertGreater(len(result), len(bits)-300)
                self.assertEqual(errors,0, reports[-1])
        dest=ROOT / "build/s3-viterbi";dest.mkdir(parents=True,exist_ok=True)
        (dest / f"decode-{mode}.json").write_text(json.dumps(reports,indent=2)+"\n")


@unittest.skipUnless(shutil.which('iverilog'), 'Icarus required')
class MetricOracleTest(unittest.TestCase):
    def test_modulo_metrics_match_unbounded_integer_oracle(self):
        rng=random.Random(0x1308192)
        pairs=[(rng.randrange(256),rng.randrange(256)) for _ in range(2048)]
        metrics=[0]*64;gold=[]
        for a,b in pairs:
            nxt=[]
            for state in range(64):
                bit=state&1;cost=[]
                for pred in (state>>1,(state>>1)+32):
                    shift=(pred<<1)|bit
                    c=[(shift&g).bit_count()&1 for g in (0o171,0o133)]
                    cost.append(metrics[pred]+sum(255-v if x else v for x,v in zip(c,(a,b))))
                nxt.append(min(cost))
            self.assertLessEqual(max(nxt)-min(nxt),3060)
            metrics=nxt;gold.append([x&8191 for x in metrics])
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory);(d/'dut.sv').write_text(trace.generate('modulo13'))
            (d/'input.hex').write_text(''.join(f'{a:02x}{b:02x}\n' for a,b in pairs))
            (d/'tb.sv').write_text(f'''module tb;
reg clk=0;always #5 clk=~clk;reg resetn=0,valid=0;reg[7:0]a,b;wire ready,ov,ob;
reg[15:0]words[0:{len(pairs)-1}];integer n=0,j,f;
s3_viterbi_traceback dut(clk,resetn,valid,ready,a,b,ov,ob);
initial begin f=$fopen("metrics.txt","w");$readmemh("input.hex",words);
repeat(4)@(negedge clk);resetn=1;
while(n<{len(pairs)}) begin @(negedge clk);valid=0;
if(ready)begin a=words[n][15:8];b=words[n][7:0];valid=1;n=n+1;end end
@(negedge clk);valid=0;repeat(4)@(negedge clk);$fclose(f);$finish;end
always @(posedge clk) if(resetn && dut.phase)begin #1;
for(j=0;j<64;j=j+1)$fwrite(f,"%x ",dut.metrics[j]);$fwrite(f,"\\n");end
endmodule''')
            subprocess.run(['iverilog','-g2012','-s','tb','-o',str(d/'sim'),str(d/'dut.sv'),str(d/'tb.sv')],check=True,capture_output=True)
            subprocess.run(['vvp',str(d/'sim')],cwd=d,check=True,capture_output=True,timeout=90)
            actual=[[int(x,16) for x in row.split()] for row in (d/'metrics.txt').read_text().splitlines()]
        self.assertEqual(len(actual),len(gold))
        self.assertEqual(actual,gold)
        dest=ROOT/'build/s3-viterbi';dest.mkdir(parents=True,exist_ok=True)
        (dest/'modulo-oracle.json').write_text(json.dumps({'steps':len(gold),'state_metrics_checked':64*len(gold),
            'all_equal_modulo_8192':True,'branch_metric_max':510,'metric_spread_bound':3060,
            'candidate_difference_bound':3570,'half_modulus':4096},indent=2)+'\n')


if __name__ == "__main__":
    unittest.main()

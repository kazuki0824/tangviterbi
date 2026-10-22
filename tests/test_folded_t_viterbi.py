"""Independent unlimited-metric oracle, encoded bits and epoch/stall checks."""
import importlib.util
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest
from experiments.folded_t_viterbi import generate

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('decoder_test', ROOT/'tests/test_s3_viterbi_decode.py')
decode = importlib.util.module_from_spec(spec); spec.loader.exec_module(decode)


def oracle(pairs):
    metrics = [0]*64
    rows = []
    for a,b in pairs:
        new=[]; decisions=0
        for state in range(64):
            costs=[]
            for pred in (state//2, state//2+32):
                word=(pred<<1)|(state&1)
                coded=[(word&g).bit_count()&1 for g in (0o171,0o133)]
                costs.append(metrics[pred]+sum(255-v if c else v for c,v in zip(coded,(a,b))))
            new.append(min(costs))
            if costs[1] < costs[0]: decisions |= 1<<state
        metrics=new
        rows.append(([m%8192 for m in metrics], decisions))
    return rows


@unittest.skipUnless(shutil.which('iverilog'), 'Icarus required')
class FoldedTest(unittest.TestCase):
    def test_arbitrary_metrics_decisions_reset_and_accept_cadence(self):
        rng=random.Random(0x221632)
        epochs=[[(rng.randrange(256),rng.randrange(256)) for _ in range(1100)],
                [(0,255),(255,0),(0,0),(255,255)]*289]
        for lanes,pipeline,compact,onehot in ((16,False,False,False),(22,False,False,False),(32,False,False,False),(16,True,False,False),(22,True,False,False),(16,False,True,False),(16,True,True,False),(16,True,True,True),(22,True,False,True)):
            with self.subTest(lanes=lanes,pipeline=pipeline,compact=compact,onehot=onehot), tempfile.TemporaryDirectory() as tmp:
                d=Path(tmp);pairs=sum(epochs,[])
                (d/'dut.sv').write_text(generate(lanes,pipeline,compact,onehot))
                (d/'input.hex').write_text(''.join(f'{a:02x}{b:02x}\n' for a,b in pairs))
                (d/'tb.sv').write_text(f'''module tb;
reg clk=0;always #5 clk=~clk;reg resetn=0,valid=0;
reg[7:0]a=0,b=0;wire ready,ov,ob;integer e,n,j,idx=0,f,t=0,last=-100;
reg[63:0] decisions;reg[15:0]words[0:{len(pairs)-1}];
folded_t_viterbi dut(clk,resetn,valid,ready,a,b,ov,ob);
initial begin $readmemh("input.hex",words);f=$fopen("metrics.txt","w");
for(e=0;e<2;e=e+1)begin
resetn=0;valid=0;repeat(4)@(negedge clk);resetn=1;n=0;last=-100;
while(n<(e==0?1100:1156))begin
@(negedge clk); valid=0;
if(ready && (e==0 || t%67<43))begin
if(e==0 && n>0 && t-last!={(64+lanes-1)//lanes+int(pipeline)})$fatal(1,"input cadence");
a=words[idx][15:8];b=words[idx][7:0];valid=1;n=n+1;idx=idx+1;last=t;end
t=t+1;end
@(negedge clk);valid=0;repeat(8)@(negedge clk);end
$fclose(f);$finish;end
always @(posedge clk)if(resetn && dut.commit_step)begin
 decisions=dut.decision_word;#1;$fwrite(f,"%0d %x ",e,decisions);
 for(j=0;j<64;j=j+1)$fwrite(f,"%x ",dut.metrics[j]);$fwrite(f,"\\n");end
endmodule''')
                subprocess.run(['iverilog','-g2012','-s','tb','-o',str(d/'sim'),str(d/'dut.sv'),str(d/'tb.sv')],check=True,capture_output=True)
                subprocess.run(['vvp',str(d/'sim')],cwd=d,check=True,capture_output=True,timeout=90)
                actual=[[] for _ in epochs]
                for line in (d/'metrics.txt').read_text().splitlines():
                    e,dec,*m=line.split();actual[int(e)].append(([int(x,16) for x in m],int(dec,16)))
                self.assertEqual(actual,[oracle(p) for p in epochs])

    def test_independent_encoder_long_stream_noise_stalls(self):
        rng=random.Random(0xF01D)
        for lanes,pipeline,compact,onehot in ((16,False,False,False),(22,False,False,False),(32,False,False,False),(16,True,False,False),(22,True,False,False),(16,False,True,False),(16,True,True,False),(16,True,True,True),(22,True,False,True)):
            for name,bits,noise,stalls in (
                ('zero',[0]*1024,False,False),('one',[1]*1024,False,False),
                ('random',[rng.randrange(2) for _ in range(16384)],True,True)):
                with self.subTest(lanes=lanes,pipeline=pipeline,compact=compact,onehot=onehot,pattern=name):
                    got=decode.run(generate(lanes,pipeline,compact,onehot),'folded_t_viterbi',bits,noise,stalls)
                    self.assertGreater(len(got),len(bits)-300)
                    self.assertEqual(got[64:],bits[64:len(got)])

    def test_dirty_reset_unknown_state_and_traceback_abort(self):
        # Reuse the independent epoch test against each exact generated RTL.
        old=decode.trace.generate
        try:
            for lanes,pipeline,compact,onehot in ((16,False,False,False),(22,False,False,False),(32,False,False,False),(16,True,False,False),(22,True,False,False),(16,False,True,False),(16,True,True,False),(16,True,True,True),(22,True,False,True)):
                with self.subTest(lanes=lanes,pipeline=pipeline,compact=compact,onehot=onehot):
                    decode.trace.generate=lambda mode: generate(lanes,pipeline,compact,onehot).replace('module folded_t_viterbi','module s3_viterbi_traceback')
                    # generate() uses a separate imported baseline function.
                    decode.DecodeTest('test_unknown_state_and_reset_aborts_inflight_traceback').test_unknown_state_and_reset_aborts_inflight_traceback()
        finally:
            decode.trace.generate=old


if __name__=='__main__':unittest.main()

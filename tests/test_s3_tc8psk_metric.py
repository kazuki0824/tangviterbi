"""Independent fixed-point distance checks and full TC8PSK information decode."""
from pathlib import Path
import sys,math,random,subprocess,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from s3_tc8psk import source
# Cardinal/diagonal Q15 constellation, indexed by (B1,Y,X), BO.1408 Fig.15.
POINTS={label:(round(32768*math.cos(k*math.pi/4)),round(32768*math.sin(k*math.pi/4)))
        for k,label in enumerate((0,1,3,2,4,5,7,6))}

def oracle(i,q):
    chosen=[];choices=0
    for xy in range(4):
        label=((xy&1)<<1)|(xy>>1)
        candidates=[POINTS[label|(w<<2)] for w in (0,1)]
        scores=[i*x+q*y for x,y in candidates]
        w=int(scores[1]>scores[0]);choices|=w<<xy;chosen.append(scores[w])
    peak=max(chosen)
    return choices<<36|sum(min(511,(peak-score+(1<<21))>>22)<<(9*n) for n,score in enumerate(chosen))

class MetricTest(unittest.TestCase):
 def run_sim(self,out,tb,dut=False,folded=False):
    out.mkdir(parents=True,exist_ok=True);(out/'tb.sv').write_text(tb)
    paths=[ROOT/('rtl/s3_tc8psk_metric_folded.sv' if folded else 'rtl/s3_tc8psk_metric.sv'),out/'tb.sv']
    if folded:(out/'tb.sv').write_text(tb.replace('s3_tc8psk_metric ', 's3_tc8psk_metric_folded '))
    if dut:(out/'dut.sv').write_text(source(True,True,22,True) if folded else source());paths.append(out/'dut.sv')
    p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),*map(str,paths)],capture_output=True,text=True)
    self.assertEqual(p.returncode,0,p.stderr)
    p=subprocess.run(['vvp','sim'],cwd=out,capture_output=True,text=True,timeout=90)
    self.assertEqual(p.returncode,0,p.stdout+p.stderr)
 def test_all_quadrants_and_stalls(self):
    self.check_all_quadrants_and_stalls(False)
 def test_folded_all_quadrants_and_stalls(self):
    self.check_all_quadrants_and_stalls(True)
 def check_all_quadrants_and_stalls(self,folded):
    out=ROOT/('build/s3-tc8psk-metric-folded' if folded else 'build/s3-tc8psk-metric');out.mkdir(parents=True,exist_ok=True)
    rng=random.Random(813);edge=(-32768,-23170,-1,0,1,23170,32767)
    samples=[(i,q) for i in edge for q in edge]+[(rng.randrange(-32768,32768),rng.randrange(-32768,32768)) for _ in range(4096)]
    (out/'input.hex').write_text(''.join(f'{((q&65535)<<16)|(i&65535):08x}\n' for i,q in samples))
    n=len(samples)
    tb=f'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,iv=0,ready=0;wire ir,ov;wire[35:0]costs;wire[3:0]choice;
reg[31:0]words[0:{n-1}];reg[31:0]w=0;integer sent=0,got=0,cycle=0,f;
s3_tc8psk_metric dut(clk,rst,iv,ir,w[15:0],w[31:16],ov,ready,costs,choice);
initial begin $readmemh("input.hex",words);f=$fopen("output.hex","w");repeat(3)@(negedge clk);rst=1;
while(got<{n})begin
 @(negedge clk);ready=cycle%17<12;iv=sent<{n}&&cycle%11!=3;if(sent<{n})w=words[sent];
 @(posedge clk);if(iv&&ir)sent=sent+1;if(ov&&ready)begin $fdisplay(f,"%010x",{{choice,costs}});got=got+1;end
 cycle=cycle+1;if(cycle>40000)$fatal(1,"stalled");
end $fclose(f);$finish;end
endmodule'''
    self.run_sim(out,tb,folded=folded)
    got=[int(v,16) for v in (out/'output.hex').read_text().split()]
    self.assertEqual(len(got),len(samples))
    for n,((i,q),actual) in enumerate(zip(samples,got)):
        self.assertEqual(actual,oracle(i,q),(n,i,q,hex(actual),hex(oracle(i,q))))
 def test_metric_plus_survivor_decodes_information(self):
    self.check_metric_plus_survivor_decodes_information(False)
 def test_folded_metric_plus_12_bit_survivor_decodes_information(self):
    self.check_metric_plus_survivor_decodes_information(True)
 def check_metric_plus_survivor_decodes_information(self,folded):
    out=ROOT/('build/s3-tc8psk-metric-folded-chain' if folded else 'build/s3-tc8psk-metric-chain');out.mkdir(parents=True,exist_ok=True)
    rng=random.Random(0x8bc);n=8192;wanted=[rng.randrange(4) for _ in range(n)];state=37;samples=[]
    for pair in wanted:
        state=((state<<1)|(pair&1))&127
        x=(state&0o171).bit_count()&1;y=(state&0o133).bit_count()&1
        p=POINTS[((pair>>1)<<2)|(y<<1)|x];a=rng.uniform(.45,.8)
        samples.append(tuple(round(v*a+rng.uniform(-600,600)) for v in p))
    (out/'input.hex').write_text(''.join(f'{((q&65535)<<16)|(i&65535):08x}\n' for i,q in samples))
    tb=f'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,iv=0;wire ir,mv,mr,ov;wire[35:0]costs;wire[3:0]choice;wire[1:0]bits;
reg[31:0]words[0:{n-1}];reg[31:0]w=0;integer sent=0,cycle=0,f;
s3_tc8psk_metric metric(clk,rst,iv,ir,w[15:0],w[31:16],mv,mr,costs,choice);
s3_tc8psk dut(clk,rst,mv,mr,costs,choice,ov,bits);
initial begin $readmemh("input.hex",words);f=$fopen("output.txt","w");repeat(4)@(negedge clk);rst=1;
while(sent<{n})begin @(negedge clk);iv=cycle%31!=7;w=words[sent];@(posedge clk);if(iv&&ir)sent=sent+1;cycle=cycle+1;end
@(negedge clk);iv=0;repeat(500)@(negedge clk);$fclose(f);$finish;end
always @(posedge clk)begin #1;if(ov)$fdisplay(f,"%0d",bits);end
endmodule'''
    self.run_sim(out,tb,True,folded)
    got=[int(v) for v in (out/'output.txt').read_text().split()]
    self.assertGreater(len(got),n-300);self.assertEqual(got[64:],wanted[64:len(got)])
    (out/'result.json').write_text(json.dumps(dict(input_symbols=n,checked_information_bits=2*(len(got)-64),error_bits=0,
      amplitude_range=[.45,.8],noise_Q15_per_axis=600,scope='FPGA metric + TC8PSK survivor; carrier/timing/TMCC/frame excluded',receiver_adopted=False),indent=2)+'\n')
if __name__=='__main__':unittest.main()

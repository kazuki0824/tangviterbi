"""Experimental FPGA cost quantizers: independent Q15 and unbounded ACS oracles."""
from pathlib import Path
import hashlib,json,math,random,subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from s3_tc8psk_precision import bound,metric_source,viterbi_source
from s3_tc8psk import source as reference_source

POINTS={label:(round(32768*math.cos(k*math.pi/4)),round(32768*math.sin(k*math.pi/4)))
        for k,label in enumerate((0,1,3,2,4,5,7,6))}
def oracle(i,q,shift):
    chosen=[];choices=0
    for xy in range(4):
        label=((xy&1)<<1)|(xy>>1)
        scores=[i*POINTS[label|(b<<2)][0]+q*POINTS[label|(b<<2)][1] for b in (0,1)]
        b=int(scores[1]>scores[0]);choices|=b<<xy;chosen.append(scores[b])
    peak=max(chosen)
    return choices<<36|sum(((peak-score+(1<<(shift-1)))>>shift)<<(9*n) for n,score in enumerate(chosen))
def label(previous,bit):
    history=(previous<<1)|bit
    return (((history&0o171).bit_count()&1)<<1)|((history&0o133).bit_count()&1)
def sim(out,paths):
    for command in (['iverilog','-g2012','-s','tb','-o','sim',*map(str,paths)],['vvp','sim']):
        p=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=120)
        with (out/'simulation.log').open('a') as f:f.write(p.stdout+p.stderr)
        if p.returncode:raise AssertionError(p.stdout+p.stderr)
    return p.stdout
def save(out,result):
    result.update(receiver_adopted=False,sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in out.glob('*.sv')})
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')

class PrecisionTest(unittest.TestCase):
 def test_bounds(self):
    expected={22:(362,1964,12),23:(181,984,11),24:(91,492,10),25:(45,248,9)}
    for shift,(cost,difference,width) in expected.items():
        b=bound(shift)
        self.assertEqual((b['maximum_cost'],b['merging_candidate_difference_bound'],b['metric_width']),(cost,difference,width))
        self.assertLess(difference,b['half_modulus'])
        self.assertFalse(b['native_RF_precision_changed'])
        self.assertFalse(b['Q15_symbol_precision_changed'])

 def test_quantizers_all_quadrants_stalls(self):
    edge=(-32768,-23170,-1,0,1,23170,32767);rng=random.Random(813)
    samples=[(i,q) for i in edge for q in edge]+[(rng.randrange(-32768,32768),rng.randrange(-32768,32768)) for _ in range(4096)]
    n=len(samples)
    for shift in (22,23,24,25):
      with self.subTest(shift=shift):
        out=ROOT/f'build/s3-precision-metric-{shift}';out.mkdir(parents=True,exist_ok=True)
        (out/'metric.sv').write_text(metric_source(shift))
        (out/'input.hex').write_text(''.join(f'{((q&65535)<<16)|(i&65535):08x}\n' for i,q in samples))
        (out/'tb.sv').write_text(f'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,iv=0,ready=0;wire ir,ov;wire[35:0]costs;wire[3:0]choice;
reg[31:0]words[0:{n-1}];reg[31:0]w=0;integer sent=0,got=0,cycle=0,f;
s3_tc8psk_metric_folded dut(clk,rst,iv,ir,w[15:0],w[31:16],ov,ready,costs,choice);
initial begin $readmemh("input.hex",words);f=$fopen("output.hex","w");repeat(3)@(negedge clk);rst=1;
while(got<{n})begin
 @(negedge clk);ready=cycle%17<12;iv=sent<{n}&&cycle%11!=3;if(sent<{n})w=words[sent];
 @(posedge clk);if(iv&&ir)sent=sent+1;if(ov&&ready)begin $fdisplay(f,"%010x",{{choice,costs}});got=got+1;end
 cycle=cycle+1;if(cycle>40000)$fatal(1,"stalled");
end $fclose(f);$finish;end
endmodule''')
        sim(out,['metric.sv','tb.sv'])
        got=[int(v,16) for v in (out/'output.hex').read_text().split()]
        self.assertEqual(got,[oracle(i,q,shift) for i,q in samples])
        self.assertLessEqual(max(w>>(9*j)&511 for w in got for j in range(4)),bound(shift)['maximum_cost'])
        save(out,dict(result='pass',shift=shift,symbols=n,output_stalls=True,proof=bound(shift)))

 def test_modulo_paths_against_unbounded_integer_and_13_bit_rtl(self):
    for shift in (23,24,25):
      with self.subTest(shift=shift):
        out=ROOT/f'build/s3-precision-acs-{shift}';out.mkdir(parents=True,exist_ok=True)
        rng=random.Random(0x140812);epochs=3;n=2048;inputs=[];expected=[];maximum=0
        edge=(-32768,-23170,-1,0,1,23170,32767)
        for epoch in range(epochs):
            metrics=[0]*64
            for s in range(n):
                if s%64<49:i,q=edge[(s%64)//7],edge[s%7]
                else:i,q=(rng.randrange(-32768,32768) for _ in range(2))
                word=oracle(i,q,shift);inputs.append(word);costs=[word>>(9*j)&511 for j in range(4)]
                updated=[]
                for destination in range(64):
                    p=destination>>1;b=destination&1
                    a=metrics[p]+costs[label(p,b)];c=metrics[p+32]+costs[label(p+32,b)]
                    maximum=max(maximum,abs(a-c));updated.append(min(a,c))
                metrics=updated;expected.append(sum((v&8191)<<(13*j) for j,v in enumerate(metrics)))
        (out/'input.hex').write_text(''.join(f'{v:010x}\n' for v in inputs))
        (out/'oracle.hex').write_text(''.join(f'{v:0208x}\n' for v in expected))
        (out/'dut.sv').write_text(viterbi_source(shift))
        (out/'reference.sv').write_text(reference_source(True,True,32).replace('module s3_tc8psk','module reference13'))
        width=bound(shift)['metric_width']
        (out/'tb.sv').write_text(f'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,iv=0;reg[39:0]word=0;wire ready,ov,rr,rv;wire[1:0]bits,rbits;
s3_tc8psk dut(clk,rst,iv,ready,word[35:0],word[39:36],ov,bits);
reference13 reference(clk,rst,iv,rr,word[35:0],word[39:36],rv,rbits);
reg[39:0]inputs[0:{epochs*n-1}];reg[831:0]expected[0:{epochs*n-1}];
integer e,s,j,index=0,checks=0,pairs=0;
initial begin $readmemh("input.hex",inputs);$readmemh("oracle.hex",expected);
 for(e=0;e<{epochs};e=e+1)begin
  @(negedge clk);rst=0;iv=0;repeat(3)@(negedge clk);rst=1;
  for(s=0;s<{n};s=s+1)begin
   @(negedge clk);iv=0;while(!ready)@(negedge clk);
   if(s%29<3)repeat(1+s%5)@(negedge clk);
   word=inputs[index];iv=1;@(posedge clk);#1;@(negedge clk);iv=0;
   @(posedge clk);#1;@(posedge clk);#1;
   for(j=0;j<64;j=j+1)begin
    if(dut.metrics[j]!==expected[index][13*j+:{width}])$fatal(1,"oracle e=%0d s=%0d state=%0d",e,s,j);
    checks=checks+1;
   end index=index+1;
  end
 end
 if(pairs<5000)$fatal(1,"insufficient output pairs");
 $display("PASS symbols=%0d state_checks=%0d output_pairs=%0d",index,checks,pairs);$finish;
end
always @(posedge clk)begin #2;if(rst)begin
 if(ready!==rr||ov!==rv||(ov&&bits!==rbits))$fatal(1,"reference mismatch");
 if(ov)pairs=pairs+1;
end end
endmodule''')
        log=sim(out,['dut.sv','reference.sv','tb.sv']);self.assertIn('PASS',log)
        self.assertLessEqual(maximum,bound(shift)['merging_candidate_difference_bound'])
        save(out,dict(result='pass',shift=shift,epochs=epochs,symbols=epochs*n,state_checks=epochs*n*64,
            maximum_observed_candidate_difference=maximum,proof=bound(shift)))

if __name__=='__main__':unittest.main()

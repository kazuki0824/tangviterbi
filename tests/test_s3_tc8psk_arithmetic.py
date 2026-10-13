"""Unbounded host ACS oracle, arbitrary costs and Q15 modulo-width contract."""
from pathlib import Path
import hashlib,json,random,subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from s3_tc8psk import source
from s3_tc8psk_metric_bound import bound
from test_s3_tc8psk_metric import oracle as q15_oracle


def label(previous,bit):
    history=(previous<<1)|bit
    return (((history&0o171).bit_count()&1)<<1)|((history&0o133).bit_count()&1)

class ArithmeticTest(unittest.TestCase):
    def test_geometric_bound(self):
        self.assertEqual(bound()['merging_candidate_difference_bound'],1964)

    def test_22_lanes_arbitrary_costs_against_unbounded_oracle(self):
        self.check_oracle(False)

    def test_q15_12_bits_against_unbounded_oracle_and_13_bits(self):
        self.check_oracle(True)

    def check_oracle(self,q15):
        out=ROOT/('build/s3-tc8psk-arithmetic-q15' if q15 else 'build/s3-tc8psk-arithmetic-arbitrary')
        out.mkdir(parents=True,exist_ok=True)
        rng=random.Random(0x140812);epochs=5;n=2048;inputs=[];expected=[];max_difference=0
        edge=(-32768,-23170,-1,0,1,23170,32767)
        for epoch in range(epochs):
            metrics=[0]*64
            for symbol in range(n):
                if q15:
                    if symbol%64<49:
                        i=edge[(symbol%64)//7];q=edge[symbol%7]
                    else:i,q=(rng.randrange(-32768,32768) for _ in range(2))
                    word=q15_oracle(i,q)
                else:
                    costs=[rng.randrange(512) for _ in range(4)]
                    if symbol%31==0:costs=[511 if (j+symbol)%2 else 0 for j in range(4)]
                    word=(rng.randrange(16)<<36)|sum(c<<(9*j) for j,c in enumerate(costs))
                inputs.append(word);costs=[word>>(9*j)&511 for j in range(4)]
                updated=[]
                for destination in range(64):
                    p=destination>>1;b=destination&1
                    a=metrics[p]+costs[label(p,b)]
                    c=metrics[p+32]+costs[label(p+32,b)]
                    max_difference=max(max_difference,abs(a-c));updated.append(min(a,c))
                metrics=updated
                expected.append(sum((value&8191)<<(13*j) for j,value in enumerate(metrics)))
        (out/'input.hex').write_text(''.join(f'{v:010x}\n' for v in inputs))
        (out/'oracle.hex').write_text(''.join(f'{v:0208x}\n' for v in expected))
        (out/'dut.sv').write_text(source(True,True,22,q15))
        (out/'reference.sv').write_text(source(True,True,22).replace('module s3_tc8psk','module reference13'))
        width=12 if q15 else 13
        tb=f'''module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0,iv=0;reg[39:0]word=0;wire ready,ov,rr,rv;wire[1:0]bits,rbits;
s3_tc8psk dut(clk,rst,iv,ready,word[35:0],word[39:36],ov,bits);
reference13 reference(clk,rst,iv,rr,word[35:0],word[39:36],rv,rbits);
reg[39:0]inputs[0:{epochs*n-1}];reg[831:0]expected[0:{epochs*n-1}];
integer e,s,j,cycle=0,index=0,checks=0,pairs=0;
initial begin
 $readmemh("input.hex",inputs);$readmemh("oracle.hex",expected);
 for(e=0;e<{epochs};e=e+1)begin
  @(negedge clk);rst=0;iv=0;repeat(3)@(negedge clk);rst=1;
  for(s=0;s<{n};s=s+1)begin
   @(negedge clk);iv=0;
   while(!ready)@(negedge clk);
   // Variable gaps plus reset while output/traceback is active between epochs.
   if(s%29<3)repeat(1+s%5)@(negedge clk);
   word=inputs[index];iv=1;
   @(posedge clk);#1;@(negedge clk);iv=0;
   @(posedge clk);#1;@(posedge clk);#1;
   for(j=0;j<64;j=j+1)begin
    if(dut.metrics[j]!==expected[index][13*j+:{width}])
     $fatal(1,"oracle e=%0d s=%0d state=%0d got=%0d expected=%0d",e,s,j,dut.metrics[j],expected[index][13*j+:{width}]);
    checks=checks+1;
   end
   index=index+1;
  end
 end
 if(pairs<8500)$fatal(1,"insufficient output comparison");
 $display("PASS epochs=%0d symbols=%0d state_checks=%0d output_pairs=%0d",{epochs},index,checks,pairs);$finish;
end
always @(posedge clk)begin #2;if(rst)begin
 if(ready!==rr||ov!==rv||(ov&&bits!==rbits))$fatal(1,"13-bit reference mismatch");
 if(ov)pairs=pairs+1;
end end
endmodule'''
        (out/'tb.sv').write_text(tb)
        p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(out/'dut.sv'),str(out/'reference.sv'),str(out/'tb.sv')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        p=subprocess.run(['vvp','sim'],cwd=out,capture_output=True,text=True,timeout=90)
        (out/'simulation.log').write_text(p.stdout+p.stderr)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertIn('PASS',p.stdout)
        self.assertLessEqual(max_difference,1964 if q15 else 3577)
        result=dict(q15_contract=q15,epochs=epochs,symbols=epochs*n,state_checks=epochs*n*64,
            maximum_observed_candidate_difference=max_difference,metric_width=width,
            oracle='unbounded Python integer ACS using independent 171/133 encoder',
            rtl_sha256=hashlib.sha256((out/'dut.sv').read_bytes()).hexdigest(),
            input_sha256=hashlib.sha256((out/'input.hex').read_bytes()).hexdigest(),
            result='pass',receiver_adopted=False)
        if q15:result['geometric_proof']=bound()
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':unittest.main()

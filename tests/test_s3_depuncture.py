from pathlib import Path
import sys,subprocess,random,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from s3_viterbi_erasure import source
# Chronological X/Y puncture entries, independently transcribed from B31 Table3-8.
MASKS=[('1','1'),('10','11'),('101','110'),('10101','11010'),('1000101','1111010')]
class DepunctureTest(unittest.TestCase):
 def test_all_rates_to_independent_source_bits(self):
  base=ROOT/'build/s3-depuncture';base.mkdir(parents=True,exist_ok=True);results=[]
  rng=random.Random(0xB31)
  for rate,(mx,my) in enumerate(MASKS):
   out=base/str(rate);out.mkdir(exist_ok=True);bits=[rng.randrange(2) for _ in range(4200)];state=27;stream=[]
   for i,b in enumerate(bits):
    state=((state<<1)|b)&127
    for g,m in zip((0o171,0o133),(mx,my)):
     if m[i%len(m)]=='1':stream.append(230 if (state&g).bit_count()&1 else 25)
   (out/'input.hex').write_text(''.join(f'{v:02x}\n' for v in stream));(out/'decoder.sv').write_text(source())
   tb=f'''module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0,fs=0,valid=0;reg[7:0]s=0;wire ready,pv,vr,ov,bitout,fault;wire[7:0]x,y;wire[1:0]erase;
s3_depuncture dp(clk,rst,fs,3'd{rate},valid,ready,s,pv,vr,x,y,erase,fault);
s3_viterbi_erasure dec(clk,rst,pv,vr,x,y,erase,ov,bitout);
reg[7:0]words[0:{len(stream)-1}];integer i=0,tick=0,f;reg accepted=0;
initial begin $readmemh("input.hex",words);f=$fopen("out.txt","w");repeat(4)@(negedge clk);rst=1;fs=1;
@(negedge clk);fs=0;
while(i<{len(stream)})begin
 @(negedge clk);if(!valid||accepted)begin valid=tick%17!=4;s=words[i];end
 @(posedge clk);accepted=valid&&ready;if(accepted)i=i+1;tick=tick+1;
end
@(negedge clk);valid=0;repeat(500)@(negedge clk);$fclose(f);$finish;end
always @(posedge clk)begin #1;if(fault)$fatal(1,"rate fault");if(ov)$fdisplay(f,"%0d",bitout);end
endmodule'''
   (out/'tb.sv').write_text(tb)
   c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(ROOT/'rtl/s3_depuncture.sv'),str(out/'decoder.sv'),str(out/'tb.sv')],text=True,capture_output=True)
   self.assertEqual(c.returncode,0,c.stderr)
   r=subprocess.run(['vvp','sim'],cwd=out,text=True,capture_output=True,timeout=90);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   got=[int(v) for v in (out/'out.txt').read_text().split()]
   self.assertGreater(len(got),len(bits)-300);self.assertEqual(got[64:],bits[64:len(got)])
   results.append(dict(rate_id=rate,transmitted_soft_values=len(stream),checked_bits=len(got)-64,errors=0))
  (base/'result.json').write_text(json.dumps(dict(rates=results,exact_erasure=True,receiver_adopted=False),indent=2)+'\n')
if __name__=='__main__':unittest.main()

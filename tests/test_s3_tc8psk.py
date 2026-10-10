"""Normative point mapping and independent TC8PSK encoder/distance stimuli."""
from pathlib import Path
import sys,math,random,subprocess,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from s3_tc8psk import source
# BO.1408 Fig15 phase labels counterclockwise from +I: (W,Y,X).
PHASE_LABELS=[0b000,0b001,0b011,0b010,0b100,0b101,0b111,0b110]
POINT={v:complex(math.cos(k*math.pi/4),math.sin(k*math.pi/4)) for k,v in enumerate(PHASE_LABELS)}
class TC8Test(unittest.TestCase):
 def test_compact_cycle_equivalence_with_reset_and_stalls(self):
  out=ROOT/'build/s3-tc8psk-equivalence';out.mkdir(parents=True,exist_ok=True)
  (out/'legacy.sv').write_text(source().replace('module s3_tc8psk','module legacy'))
  (out/'compact.sv').write_text(source(True))
  (out/'b1.sv').write_text(source(True,True).replace('module s3_tc8psk','module compact_b1'))
  (out/'parallel.sv').write_text(source(True,True,parallel_traceback_choice=True).replace('module s3_tc8psk','module parallel_b1'))
  tb='''module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0,iv=0;reg[39:0] stimulus=0;wire ra,rb,rc,rd,va,vb,vc,vd;wire[1:0]a,b,d,p;
legacy old(clk,rst,iv,ra,stimulus[35:0],stimulus[39:36],va,a);
s3_tc8psk dut(clk,rst,iv,rb,stimulus[35:0],stimulus[39:36],vb,b);
compact_b1 third(clk,rst,iv,rc,stimulus[35:0],stimulus[39:36],vc,d);
parallel_b1 fourth(clk,rst,iv,rd,stimulus[35:0],stimulus[39:36],vd,p);
reg[63:0] rng=64'hadb876aa456ff214;integer e,c,checked=0;
initial begin
for(e=0;e<9;e=e+1)begin
 @(negedge clk);rst=0;iv=0;repeat(4)@(negedge clk);rst=1;
 // Reset at different traceback/output phases, arbitrary bounded metrics,
 // and long pauses test that RAM contents never leak across an epoch.
 for(c=0;c<5000+e*11;c=c+1)begin
  @(negedge clk);rng=rng^(rng<<13);rng=rng^(rng>>7);rng=rng^(rng<<17);
  iv=ra&&(c%71<63);stimulus=rng[39:0];
  @(posedge clk);#1;
  if(ra!==rb||ra!==rc||ra!==rd||va!==vb||va!==vc||va!==vd||(va&&(a!==b||a!==d||a!==p)))$fatal(1,"cycle mismatch epoch=%0d c=%0d",e,c);
  if(va)checked=checked+1;
 end
end
if(checked<12000)$fatal(1,"coverage");
$display("PASS epochs=9 cycles=45396 checked_pairs=%0d",checked);$finish;
end
endmodule'''
  (out/'tb.sv').write_text(tb)
  c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(out/'legacy.sv'),str(out/'compact.sv'),str(out/'b1.sv'),str(out/'parallel.sv'),str(out/'tb.sv')],text=True,capture_output=True)
  self.assertEqual(c.returncode,0,c.stderr)
  r=subprocess.run(['vvp','sim'],cwd=out,text=True,capture_output=True,timeout=90)
  (out/'simulation.log').write_text(r.stdout+r.stderr)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS',r.stdout)
 def test_coded_and_uncoded_traceback(self):
  self.check_coded_and_uncoded_traceback(False)
 def test_compact_coded_and_uncoded_traceback(self):
  self.check_coded_and_uncoded_traceback(True)
 def test_compact_branch_choice_traceback(self):
  self.check_coded_and_uncoded_traceback(True,True)
 def test_22_lane_traceback(self):
  self.check_coded_and_uncoded_traceback(True,True,22)
 def check_coded_and_uncoded_traceback(self,compact,b1=False,lanes=32):
  name='build/s3-tc8psk-compact' if compact else 'build/s3-tc8psk'
  if b1:name+='-b1'
  if lanes==22:name+='-acs22'
  out=ROOT/name;out.mkdir(parents=True,exist_ok=True)
  rng=random.Random(0x1408);n=8192;wanted=[rng.randrange(4) for _ in range(n)]
  state=37;stim=[]
  for pair in wanted:
   state=((state<<1)|(pair&1))&127
   x=(state&0o171).bit_count()&1;y=(state&0o133).bit_count()&1
   z=POINT[((pair>>1)<<2)|(y<<1)|x]+complex(rng.uniform(-.035,.035),rng.uniform(-.035,.035))
   metrics=[];choices=0
   for xy in range(4):
    label=((xy&1)<<1)|(xy>>1)
    ds=[abs(z-POINT[label|(w<<2)])**2 for w in (0,1)]
    w=0 if ds[0]<=ds[1] else 1;choices|=w<<xy
    metrics.append(min(511,128+round(ds[w]*120)))
   stim.append((choices<<36)|sum(v<<(9*i) for i,v in enumerate(metrics)))
  (out/'dut.sv').write_text(source(compact,b1,lanes));(out/'input.hex').write_text(''.join(f'{v:010x}\n' for v in stim))
  tb=f'''module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0,valid=0;wire ready,ov;wire[1:0]bits;
reg[39:0]w[0:{n-1}];reg[39:0]input_word=0;
s3_tc8psk dut(clk,rst,valid,ready,input_word[35:0],input_word[39:36],ov,bits);
integer i=0,cycle=0,f;
initial begin $readmemh("input.hex",w);f=$fopen("output.txt","w");repeat(4)@(negedge clk);rst=1;
while(i<{n})begin @(negedge clk);valid=0;
if(ready&&cycle%31!=7)begin input_word=w[i];valid=1;i=i+1;end
cycle=cycle+1;end
@(negedge clk);valid=0;repeat(400)@(negedge clk);$fclose(f);$finish;end
always @(posedge clk)begin #1;if(ov)$fdisplay(f,"%0d",bits);end
endmodule'''
  (out/'tb.sv').write_text(tb)
  c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(out/'dut.sv'),str(out/'tb.sv')],text=True,capture_output=True)
  self.assertEqual(c.returncode,0,c.stderr)
  r=subprocess.run(['vvp','sim'],cwd=out,text=True,capture_output=True,timeout=90);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  got=[int(v) for v in (out/'output.txt').read_text().split()]
  self.assertGreater(len(got),n-300);self.assertEqual(got[64:],wanted[64:len(got)])
  report=dict(compact_output=compact,compact_b1=b1,acs_lanes=lanes,symbols=n,checked_information_bits=2*(len(got)-64),unknown_initial_state=37,noise='bounded +/-0.035 per axis',
     error_bits=0,input_cost_bits=9,parallel_branch_choice_preserved=True,common_cost_per_symbol=128,metric_wraps_exercised=True,
     scope='TC8PSK traceback; metric generation is a host oracle, RF/carrier/TMCC/frame excluded',receiver_adopted=False,
     source='https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf')
  (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':unittest.main()

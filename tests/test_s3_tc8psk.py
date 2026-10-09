"""Normative point mapping and independent TC8PSK encoder/distance stimuli."""
from pathlib import Path
import sys,math,random,subprocess,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from s3_tc8psk import source
# BO.1408 Fig15 phase labels counterclockwise from +I: (W,Y,X).
PHASE_LABELS=[0b000,0b001,0b011,0b010,0b100,0b101,0b111,0b110]
POINT={v:complex(math.cos(k*math.pi/4),math.sin(k*math.pi/4)) for k,v in enumerate(PHASE_LABELS)}
class TC8Test(unittest.TestCase):
 def test_coded_and_uncoded_traceback(self):
  out=ROOT/'build/s3-tc8psk';out.mkdir(parents=True,exist_ok=True)
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
  (out/'dut.sv').write_text(source());(out/'input.hex').write_text(''.join(f'{v:010x}\n' for v in stim))
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
  report=dict(symbols=n,checked_information_bits=2*(len(got)-64),unknown_initial_state=37,noise='bounded +/-0.035 per axis',
     error_bits=0,input_cost_bits=9,parallel_branch_choice_preserved=True,common_cost_per_symbol=128,metric_wraps_exercised=True,
     scope='TC8PSK traceback; metric generation is a host oracle, RF/carrier/TMCC/frame excluded',receiver_adopted=False,
     source='https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf')
  (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':unittest.main()

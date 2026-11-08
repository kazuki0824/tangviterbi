"""Exact zero-weight punctures: independent encoder and unlimited oracle."""
from pathlib import Path
import random,shutil,subprocess,tempfile,unittest,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"experiments"))
from s3_viterbi_erasure import source as baseline_erasure
from experiments.folded_t_viterbi import generate

def reference(words):
 metrics=[0]*64;rows=[]
 for a,b,erase in words:
  nxt=[];decisions=0
  for state in range(64):
   costs=[]
   for pred in (state//2,state//2+32):
    w=(pred<<1)|(state&1)
    bits=[(w&g).bit_count()&1 for g in (0o171,0o133)]
    costs.append(metrics[pred]+sum(0 if erase&(2>>i) else (255-v if bit else v) for i,(bit,v) in enumerate(zip(bits,(a,b)))))
   nxt.append(min(costs))
   if costs[1]<costs[0]:decisions|=1<<state
  metrics=nxt;rows.append(([v%8192 for v in metrics],decisions))
 return rows

@unittest.skipUnless(shutil.which('iverilog'),'Icarus required')
class ErasureTest(unittest.TestCase):
 def test_metrics_and_all_T_code_rates(self):
  for registered in (False,True,"baseline","shift"):
   with self.subTest(registered_costs=registered):self.check_variant(registered)
 def test_final_inflight_reset(self):
  self.check_reset(True)
 def test_registered_inflight_reset(self):
  self.check_reset(False)
 def check_reset(self,shift):
  import importlib.util
  spec=importlib.util.spec_from_file_location('old_decode_test',Path(__file__).with_name('test_s3_viterbi_decode.py'))
  mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
  rtl=generate(16,True,True,True,True,True,shift).replace('module folded_t_viterbi','module s3_viterbi_traceback')
  rtl=rtl.replace('    input wire [1:0] erasure,\n','').replace('    localparam [METRIC_W-1:0] INF',"    wire [1:0] erasure=0;\n    localparam [METRIC_W-1:0] INF")
  mod.trace.generate=lambda mode:rtl
  mod.DecodeTest('test_unknown_state_and_reset_aborts_inflight_traceback').test_unknown_state_and_reset_aborts_inflight_traceback()
 def check_variant(self,registered):
  cadence=2 if registered=="baseline" else (6 if registered else 5)
  rng=random.Random(7133);epochs=[];wanted=[]
  epochs.append([(rng.randrange(256),rng.randrange(256),rng.randrange(4)) for _ in range(2048)]);wanted.append(None)
  for x,y in [('1','1'),('10','11'),('101','110'),('10101','11010'),('1000101','1111010')]:
   bits=[rng.randrange(2) for _ in range(2048)];state=37;words=[]
   for i,bit in enumerate(bits):
    state=((state<<1)|bit)&127
    coded=[(state&g).bit_count()&1 for g in (0o171,0o133)]
    erase=(2 if x[i%len(x)]=='0' else 0)|(1 if y[i%len(y)]=='0' else 0)
    words.append((230 if coded[0] else 25,230 if coded[1] else 25,erase))
   epochs.append(words);wanted.append(bits)
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp);(d/'dut.sv').write_text(baseline_erasure().replace('module s3_viterbi_erasure','module folded_t_viterbi') if registered=='baseline' else generate(16,True,True,True,True,bool(registered),registered=="shift"))
   (d/'input.hex').write_text(''.join(f'{(a<<10)|(b<<2)|e:05x}\n' for ep in epochs for a,b,e in ep))
   tb='''module tb;
reg clk=0;always #5 clk=~clk;reg resetn=0,valid=0;reg[7:0]a=0,b=0;reg[1:0]erase=0;
wire ready,ov,ob;integer e,n,j,idx=0,t=0,f,g,last=-100;reg[63:0]decisions;reg[17:0]words[0:12287];
folded_t_viterbi dut(clk,resetn,valid,ready,a,b,erase,ov,ob);
initial begin $readmemh("input.hex",words);f=$fopen("metrics.txt","w");g=$fopen("bits.txt","w");
for(e=0;e<6;e=e+1)begin
resetn=0;valid=0;repeat(4)@(negedge clk);resetn=1;n=0;last=-100;
while(n<2048)begin
@(negedge clk);valid=0;
if(ready && (e==0 || t%127<101))begin
if(e==0 && n>0 && t-last!=EXPECTED_CADENCE)$fatal(1,"continuous input cadence");last=t;
{a,b,erase}=words[idx];valid=1;idx=idx+1;n=n+1;end
t=t+1;end
@(negedge clk);valid=0;repeat(400)@(negedge clk);end
$fclose(f);$fclose(g);$finish;end
always @(posedge clk)begin
 if(resetn && dut.commit_step)begin decisions=dut.decision_word;#1;
 $fwrite(f,"%0d %x ",e,decisions);for(j=0;j<64;j=j+1)$fwrite(f,"%x ",dut.metrics[j]);$fwrite(f,"\\n");end
end
always @(posedge clk)begin #1;if(resetn && ov)$fdisplay(g,"%0d %0d",e,ob);end
endmodule'''
   if registered=='baseline':
    tb=tb.replace('dut.commit_step','(dut.initialized && dut.phase)').replace('dut.decision_word','{dut.lane_decision,dut.decision_partial}')
   tb=tb.replace('EXPECTED_CADENCE',str(cadence))
   (d/'tb.sv').write_text(tb)
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(d/'sim'),str(d/'dut.sv'),str(d/'tb.sv')],check=True,capture_output=True)
   subprocess.run(['vvp',str(d/'sim')],cwd=d,check=True,capture_output=True,timeout=90)
   actual=[[] for _ in epochs];bits=[[] for _ in epochs]
   for line in (d/'metrics.txt').read_text().splitlines():
    e,dec,*m=line.split();actual[int(e)].append(([int(v,16) for v in m],int(dec,16)))
   for line in (d/'bits.txt').read_text().splitlines():
    e,v=map(int,line.split());bits[e].append(v)
  for e,ep in enumerate(epochs):
   self.assertEqual(actual[e],reference(ep),e)
   if wanted[e] is not None:
    self.assertGreater(len(bits[e]),1800,e)
    self.assertEqual(bits[e][64:],wanted[e][64:len(bits[e])],e)
if __name__=='__main__':unittest.main()

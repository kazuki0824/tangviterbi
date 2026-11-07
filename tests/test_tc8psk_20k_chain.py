"""Known TC8PSK data and sustained-rate check for the measured 20K chains."""
import hashlib,json,math,os,random,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from s3_tc8psk import source
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ChainTest(unittest.TestCase):
 def test_lanes_and_sustained_rate(self):
  rng=random.Random(0x8bc);n=8192;wanted=[rng.randrange(4)for _ in range(n)];state=37;samples=[]
  points={label:(round(32768*math.cos(k*math.pi/4)),round(32768*math.sin(k*math.pi/4)))for k,label in enumerate((0,1,3,2,4,5,7,6))}
  for pair in wanted:
   state=((state<<1)|(pair&1))&127;x=(state&0o171).bit_count()&1;y=(state&0o133).bit_count()&1
   p=points[((pair>>1)<<2)|(y<<1)|x];amp=rng.uniform(.45,.8)
   samples.append(tuple(round(v*amp+rng.uniform(-600,600))for v in p))
  results=[]
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'input.hex').write_text(''.join(f'{((q&65535)<<16)|(i&65535):08x}\n'for i,q in samples))
   tb=r'''module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,iv=0;reg[31:0]word=0;wire ir,ov;wire[1:0]bits;
s_tc8psk_chain dut(clk,resetn,iv,ir,word[15:0],word[31:16],ov,bits);
reg[31:0]words[0:8191];integer sent=0,cycle=0,first=-1,last=-1,max_gap=0,f;
initial begin
 $readmemh("input.hex",words);f=$fopen("output.txt","w");
 repeat(4)@(negedge clk);resetn=1;
 while(sent<8192)begin
  @(negedge clk);iv=1;word=words[sent];
  @(posedge clk);
  if(iv && ir)begin
   if(first<0)first=cycle;
   if(last>=0 && cycle-last>max_gap)max_gap=cycle-last;
   last=cycle;sent=sent+1;
  end
  cycle=cycle+1;
  if(cycle>50000)$fatal(1,"rate timeout");
 end
 @(negedge clk);iv=0;repeat(600)@(negedge clk);
 if(max_gap>3 || last-first!=3*(8192-1))$fatal(1,"continuous rate loss");
 $display("PASS symbols=%0d first=%0d last=%0d max_gap=%0d",sent,first,last,max_gap);$finish;
end
always @(posedge clk)begin #1;if(resetn && ov)$fdisplay(f,"%0d",bits);end
endmodule'''
   (p/'tb.sv').write_text(tb)
   for lanes in (22,32):
    with self.subTest(lanes=lanes):
     generated=source(True,True,lanes,True);(p/'survivor.sv').write_text(generated)
     files=[p/'tb.sv',p/'survivor.sv',ROOT/'rtl/s3_tc8psk_metric_folded.sv',ROOT/'rtl/s_tc8psk_chain.sv']
     subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),*map(str,files)],check=True)
     r=subprocess.run(['vvp',str(p/'sim')],cwd=d,capture_output=True,text=True,timeout=90)
     self.assertEqual(r.returncode,0,r.stdout+r.stderr);print('lanes',lanes,r.stdout.strip(),flush=True)
     got=[int(x)for x in (p/'output.txt').read_text().split()]
     self.assertGreater(len(got),n-300);self.assertEqual(got[64:],wanted[64:len(got)])
     results.append(dict(lanes=lanes,summary=r.stdout.strip(),input_symbols=n,output_pairs=len(got),checked_information_bits=2*(len(got)-64),error_bits=0,generated_sha256=hashlib.sha256(generated.encode()).hexdigest()))
  result=dict(scope=__doc__,results=results,source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()for f in [Path(__file__),ROOT/'rtl/s3_tc8psk_metric_folded.sv',ROOT/'rtl/s_tc8psk_chain.sv',ROOT/'experiments/s3_tc8psk.py',ROOT/'experiments/s3_viterbi_traceback.py']},whole_receiver_verified=False)
  if os.environ.get('TC8PSK_20K_TEST_REPORT'):Path(os.environ['TC8PSK_20K_TEST_REPORT']).write_text(json.dumps(result,indent=2)+'\n')

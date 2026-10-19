"""All puncture phases and stable pairs under backpressure with isolated input ready."""
import random,shutil,subprocess,tempfile,unittest
from pathlib import Path
from tests.test_shared_k7_depuncture_stream import MASKS
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class IsolatedDepunctureTest(unittest.TestCase):
 def test_all_rates_pair_oracle_and_stalls(self):
  rng=random.Random(201030);words=[];expected=[];lengths=[]
  for mx,my in MASKS:
   stream=[];pairs=[]
   for j in range(420):
    a,b=rng.randrange(256),rng.randrange(256);er=0
    if mx[j%len(mx)]=='1':stream.append(a)
    else:a=0;er|=2
    if my[j%len(my)]=='1':stream.append(b)
    else:b=0;er|=1
    pairs.append((a,b,er))
   words+=stream+[0]*(1024-len(stream));lengths.append(len(stream));expected.append(pairs)
  tb=r'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,fs=0,iv=0,orr=0;reg[2:0]rate=0;reg[7:0]s=0;
wire ir,ov,fault;wire[7:0]x,y;wire[1:0]er;s3_depuncture_isolated dut(clk,rst,fs,rate,iv,ir,s,ov,orr,x,y,er,fault);
reg[7:0]words[0:5119];integer lengths[0:4];integer r,j,t=0,f;reg accepted=0,held_valid=0;reg[17:0]held;
initial begin
 INIT
 $readmemh("input.hex",words);f=$fopen("pairs.txt","w");
 repeat(3)@(negedge clk);rst=1;fs=1;rate=7;@(negedge clk);fs=0;repeat(2)@(negedge clk);
 if(!fault||ir)$fatal(1,"invalid rate accepted");
 for(r=0;r<5;r=r+1)begin
  rst=0;iv=0;held_valid=0;repeat(3)@(negedge clk);rst=1;fs=1;rate=r;
  @(negedge clk);fs=0;j=0;accepted=0;
  while(j<lengths[r])begin
   @(negedge clk);orr=t%7!=2&&t%7!=3;
   if(!iv||accepted)begin iv=t%17!=9;s=words[r*1024+j];end
   @(posedge clk);accepted=iv&&ir;if(accepted)j=j+1;t=t+1;
  end
  @(negedge clk);iv=0;orr=1;repeat(50)@(negedge clk);
 end
 $fclose(f);$finish;
end
always @(posedge clk)begin
 if(rst&&!fs&&!fault)begin
  if(held_valid&&(!ov||{x,y,er}!==held))$fatal(1,"pair changed under stall");
  held_valid=ov&&!orr;held={x,y,er};
  if(ov&&orr)$fdisplay(f,"%0d %0d %0d %0d",r,x,y,er);
  if(ov&&ir)$fatal(1,"input-ready bypass remained");
 end
end
endmodule'''.replace('INIT',''.join(f'lengths[{i}]={n};'for i,n in enumerate(lengths)))
  with tempfile.TemporaryDirectory() as temp:
   d=Path(temp);(d/'input.hex').write_text(''.join(f'{v:02x}\n'for v in words));(d/'tb.sv').write_text(tb)
   p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(d/'sim'),str(ROOT/'experiments/s3_depuncture_isolated.sv'),str(d/'tb.sv')],text=True,capture_output=True);self.assertEqual(p.returncode,0,p.stderr)
   p=subprocess.run(['vvp',str(d/'sim')],cwd=d,text=True,capture_output=True);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
   actual=[[]for i in range(5)]
   for line in (d/'pairs.txt').read_text().splitlines():
    r,x,y,er=map(int,line.split());actual[r].append((x,y,er))
  self.assertEqual(actual,expected);print('PASS 2100 pairs; all five rates, arbitrary 8-bit soft, erasures, output stalls, invalid rate')
if __name__=='__main__':unittest.main()

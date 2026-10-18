"""Exercise actual queues/scheduler against independent Viterbi oracle."""
import importlib.util
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('oracle',ROOT/'tests/test_folded_t_erasures.py')
oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)

@unittest.skipUnless(shutil.which('iverilog'), 'Icarus required')
class StreamTest(unittest.TestCase):
 def test_round_robin_queues_and_reset(self):
  self.check_variant(0)
 def test_weighted_queues_and_reset(self):
  self.check_variant(1)
 def check_variant(self,weighted):
  rng=random.Random(1801);n=512;epochs=[];bits=[];order=[]
  for ep in range(3):
   streams=[];expected=[]
   for c in range(4):
    b=[rng.randrange(2) for _ in range(n)];state=rng.randrange(64);words=[]
    patterns=[('1','1'),('10','11'),('101','110'),('10101','11010'),('1000101','1111010')]
    x,y=patterns[(ep+c)%5]
    for j,bit in enumerate(b):
     state=((state<<1)|bit)&127
     erase=(2 if x[j%len(x)]=='0' else 0)|(1 if y[j%len(y)]=='0' else 0)
     a,d=[230 if (state&g).bit_count()%2 else 25 for g in (0o171,0o133)]
     words.append((a,d,erase) if ep else (rng.randrange(256),rng.randrange(256),rng.randrange(4)))
    streams.append(words);expected.append(b)
   epochs.append(streams);bits.append(expected)
   ids=[c for c in range(4) for _ in range(n)]
   if ep!=1:rng.shuffle(ids)
   order+=ids
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp)
   (d/'words.hex').write_text(''.join(f'{(a<<10)|(b<<2)|e:05x}\n' for ep in epochs for st in ep for a,b,e in st))
   (d/'order.hex').write_text(''.join(f'{c:x}\n' for c in order))
   (d/'tb.sv').write_text(r'''module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,iv=0;wire ir,ov,ob;reg[1:0]ctx=0;wire[1:0]oc;
reg[17:0]word=0;
shared_k7_stream #(.WEIGHTED(WEIGHT_OPTION)) dut(clk,resetn,iv,ir,ctx,word[17:10],word[9:2],word[1:0],ov,ob,oc);
reg[17:0]words[0:6143];reg[1:0]order[0:6143];
integer ep,j,c,k,f,g,committed,cycles=0,stalls=0;integer counts[0:3];
integer last_data[0:3];integer last_idle[0:3];integer slot_no=0;reg[63:0]decision;
initial begin
 $readmemh("words.hex",words);$readmemh("order.hex",order);
 f=$fopen("metrics.txt","w");g=$fopen("bits.txt","w");
 for(ep=0;ep<3;ep=ep+1)begin
  resetn=0;iv=0;repeat(3)@(negedge clk);resetn=1;
  for(c=0;c<4;c=c+1)begin counts[c]=0;last_data[c]=0;last_idle[c]=0;end
  slot_no=0;
  for(j=0;j<2048;j=j+1)begin
   @(negedge clk);c=order[ep*2048+j];ctx=c;word=words[ep*2048+c*512+counts[c]];iv=1;
   @(posedge clk);
   while(!ir)begin stalls=stalls+1;@(posedge clk);end
   counts[c]=counts[c]+1;
   // Keep the producer valid under pressure; occasionally let all queues drain.
   if(j%137==0)begin @(negedge clk);iv=0;repeat(37)@(negedge clk);end
  end
  @(negedge clk);iv=0;
  repeat(1600)@(negedge clk);
  // Flush dirty queues and an in-flight slot with a global reset.
  ctx=3;word=18'h2ffff;iv=1;repeat(21)@(negedge clk);resetn=0;iv=0;
 end
 if(stalls==0)$fatal(1,"no full-queue coverage");
 $display("PASS: full-queue stall cycles=%0d",stalls);$finish;
end
always @(posedge clk)begin
 cycles=cycles+1;if(cycles>100000)$fatal(1,"timeout");
 if(resetn&&dut.prepare&&!dut.boot)begin
  slot_no=slot_no+1;
  if(!dut.data_slot)last_idle[dut.selected]=slot_no;
  if(dut.pop)last_data[dut.selected]=slot_no;
  for(integer z=0;z<4;z=z+1)begin
   if(slot_no-last_idle[z]>512)$fatal(1,"idle service starvation");
   if(!dut.nonempty[z])last_data[z]=slot_no;
   if(slot_no-last_data[z]>11)$fatal(1,"nonempty queue starvation");
  end
 end
 if(resetn&&dut.core.tick&&dut.core.initialized[dut.core.context_id]&&dut.core.phase)begin
  committed=dut.core.context_id;decision={dut.core.lane_decision,dut.core.decision_partial};#1;
  $fwrite(f,"%0d %0d %x ",ep,committed,decision);
  for(k=0;k<64;k=k+1)$fwrite(f,"%x ",dut.core.metrics[64*committed+k]);$fwrite(f,"\n");
 end
end
always @(posedge clk)begin #1;if(resetn&&ov)$fdisplay(g,"%0d %0d %0d",ep,oc,ob);end
endmodule'''.replace("WEIGHT_OPTION",str(weighted)))
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(d/'sim'),str(ROOT/'rtl/shared_k7_context.sv'),str(ROOT/'rtl/shared_k7_stream.sv'),str(d/'tb.sv')],check=True,capture_output=True)
   p=subprocess.run(['vvp',str(d/'sim')],cwd=d,check=True,capture_output=True,text=True,timeout=180)
   actual=[[[] for _ in range(4)] for _ in epochs];outputs=[[[] for _ in range(4)] for _ in epochs]
   for line in (d/'metrics.txt').read_text().splitlines():
    ep,c,dec,*m=line.split();actual[int(ep)][int(c)].append(([int(v,16)for v in m],int(dec,16)))
   for line in (d/'bits.txt').read_text().splitlines():
    ep,c,b=map(int,line.split());outputs[ep][c].append(b)
   print(p.stdout.strip())
  for ep in range(3):
   for c in range(4):
    with self.subTest(epoch=ep,context=c):
     # Extra dirty words immediately before reset are outside the 512-word fixture.
     self.assertEqual(actual[ep][c][:n],oracle.reference(epochs[ep][c]))
     self.assertGreater(len(outputs[ep][c]),380)
     if ep:self.assertEqual(outputs[ep][c][64:],bits[ep][c][64:len(outputs[ep][c])])
if __name__=='__main__':unittest.main()

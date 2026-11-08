"""End-to-end interleaved punctured soft input -> shared K7 decisions/bits."""
import importlib.util,random,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('oracle',ROOT/'tests/test_folded_t_erasures.py')
oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
MASKS=[('1','1'),('10','11'),('101','110'),('10101','11010'),('1000101','1111010')]
@unittest.skipUnless(shutil.which('iverilog'),'Icarus required')
class DepuncturedStreamTest(unittest.TestCase):
 def test_all_rates_interleaved_phases_full_queues_and_reset(self):
  rng=random.Random(180218);epochs=[];expected=[];inputs=[];order=[];lengths=[]
  for ep in range(5):
   streams=[];bits4=[];ids=[]
   for c in range(4):
    bits=[rng.randrange(2) for _ in range(512)];state=rng.randrange(64);pairs=[];soft=[]
    x,y=MASKS[(ep+c)%5]
    for j,b in enumerate(bits):
     state=((state<<1)|b)&127;raw=[230 if (state&g).bit_count()%2 else 25 for g in (0o171,0o133)]
     erase=0;pair=[]
     for k,m in enumerate((x,y)):
      if m[j%len(m)]=='1':pair.append(raw[k]);soft.append(raw[k])
      else:pair.append(0);erase|=2>>k
     pairs.append((*pair,erase))
    streams.append(pairs);bits4.append(bits);inputs+=soft+[0]*(1024-len(soft));ids += [c]*len(soft)
   rng.shuffle(ids);lengths.append(len(ids));order+=ids+[0]*(4096-len(ids));epochs.append(streams);expected.append(bits4)
  with tempfile.TemporaryDirectory() as temp:
   d=Path(temp);(d/'soft.hex').write_text(''.join(f'{x:02x}\n' for x in inputs));(d/'order.hex').write_text(''.join(f'{x:x}\n' for x in order))
   tb=r'''module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0,iv=0;reg[11:0]rates=0;reg[1:0]ctx=0;reg[7:0]llr=0;
wire ir,ov,ob;wire[1:0]oc;wire[3:0]fault;
shared_k7_depuncture_stream dut(clk,rst,rates,iv,ir,ctx,llr,ov,ob,oc,fault);
reg[7:0]words[0:20479];reg[1:0]order[0:20479];
integer lengths[0:4];integer ep,j,c,k,f,g,who,stalls=0,cycles=0,bypass=0;integer count[0:3];reg observe=0;reg[63:0]decision;
initial begin
 LENGTH_INIT
 $readmemh("soft.hex",words);$readmemh("order.hex",order);
 f=$fopen("metrics.txt","w");g=$fopen("bits.txt","w");
 // Invalid rate blocks its input and raises that context's fault.
 repeat(3)@(negedge clk);rates=12'hfff;rst=1;repeat(4)@(negedge clk);
 if(fault!=15||ir)$fatal(1,"invalid rates accepted");
 for(ep=0;ep<5;ep=ep+1)begin
  rst=0;iv=0;observe=0;
  for(c=0;c<4;c=c+1)begin rates[3*c+:3]=(ep+c)%5;count[c]=0;end
  repeat(3)@(negedge clk);rst=1;observe=1;
  for(j=0;j<lengths[ep];j=j+1)begin
   @(negedge clk);c=order[4096*ep+j];ctx=c;llr=words[4096*ep+1024*c+count[c]];iv=1;
   @(posedge clk);while(!ir)begin stalls=stalls+1;@(posedge clk);end
   count[c]=count[c]+1;
   if(j%113==0)begin @(negedge clk);iv=0;repeat(11)@(negedge clk);end
  end
  @(negedge clk);iv=0;repeat(1700)@(negedge clk);observe=0;
  // Dirty partial X/Y and queue state must not leak across reset.
  ctx=0;llr=77;iv=1;repeat(15)@(negedge clk);rst=0;iv=0;
 end
 if(bypass==0)$fatal(1,"no full-context bypass coverage");
 if(stalls==0)$fatal(1,"no backpressure exercised");
 $display("PASS: stalls=%0d, bypass=%0d",stalls,bypass);$finish;
end
always @(posedge clk)begin
 cycles=cycles+1;if(cycles>150000)$fatal(1,"timeout");
 if(observe&&rst&&!dut.configuring && |(dut.pair_valid & dut.context_ready))begin
  if(!(dut.found&&dut.queue_ready))$fatal(1,"eligible context blocked behind full FIFO");
  if(|(dut.pair_valid & ~dut.context_ready))bypass=bypass+1;
 end
 if(observe&&rst&&fault)$fatal(1,"unexpected fault");
 if(observe&&rst&&dut.stream.core.tick&&dut.stream.core.initialized[dut.stream.core.context_id]&&dut.stream.core.phase)begin
  who=dut.stream.core.context_id;decision={dut.stream.core.lane_decision,dut.stream.core.decision_partial};#1;
  $fwrite(f,"%0d %0d %x ",ep,who,decision);
  for(k=0;k<64;k=k+1)$fwrite(f,"%x ",dut.stream.core.metrics[64*who+k]);$fwrite(f,"\n");
 end
end
always @(posedge clk)begin #1;if(observe&&rst&&ov)$fdisplay(g,"%0d %0d %0d",ep,oc,ob);end
endmodule'''.replace('LENGTH_INIT',''.join(f'lengths[{e}]={n};' for e,n in enumerate(lengths)))
   (d/'tb.sv').write_text(tb)
   files=['rtl/shared_k7_context.sv','rtl/shared_k7_stream.sv','rtl/s3_depuncture.sv','rtl/shared_k7_depuncture_stream.sv']
   c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(d/'sim'),*[str(ROOT/f) for f in files],str(d/'tb.sv')],capture_output=True,text=True);self.assertEqual(c.returncode,0,c.stderr)
   p=subprocess.run(['vvp',str(d/'sim')],cwd=d,capture_output=True,text=True,timeout=180);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
   actual=[[[] for _ in range(4)] for _ in epochs];bits=[[[] for _ in range(4)] for _ in epochs]
   for line in (d/'metrics.txt').read_text().splitlines():
    e,c,dec,*m=line.split();actual[int(e)][int(c)].append(([int(x,16)for x in m],int(dec,16)))
   for line in (d/'bits.txt').read_text().splitlines():
    e,c,b=map(int,line.split());bits[e][c].append(b)
   print(p.stdout)
  for e in range(5):
   for c in range(4):
    with self.subTest(epoch=e,context=c):
     self.assertEqual(actual[e][c],oracle.reference(epochs[e][c]))
     self.assertGreater(len(bits[e][c]),380)
     self.assertEqual(bits[e][c][64:],expected[e][c][64:len(bits[e][c])])
if __name__=='__main__':unittest.main()

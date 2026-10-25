"""Independent metrics/decisions and clean encoded streams across three contexts."""
import importlib.util
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('erasure_oracle',ROOT/'tests/test_folded_t_erasures.py')
oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)

@unittest.skipUnless(shutil.which('iverilog'),'Icarus required')
class CooleScheduledContextTest(unittest.TestCase):
 def test_split_banks(self):
  self.check_variant()
 def check_variant(self):
  rng=random.Random(713304);n=1024;epochs=[];wanted=[];schedule=[]
  patterns=[('1','1'),('10','11'),('101','110'),('10101','11010'),('1000101','1111010')]
  for epoch in range(6):
   streams=[];bits4=[]
   for c in range(3):
    bits=[rng.randrange(2) for _ in range(n)];state=rng.randrange(64);words=[]
    x,y=patterns[(epoch+c)%5]
    for j,bit in enumerate(bits):
     state=((state<<1)|bit)&127
     coded=[(state&g).bit_count()&1 for g in (0o171,0o133)]
     erase=(2 if x[j%len(x)]=='0' else 0)|(1 if y[j%len(y)]=='0' else 0)
     words.append((230 if coded[0] else 25,230 if coded[1] else 25,erase) if epoch else
                  (rng.randrange(256),rng.randrange(256),rng.randrange(3)))
    streams.append(words);bits4.append(bits)
   epochs.append(streams);wanted.append(bits4)
   ids=[c for c in range(3) for _ in range(n)]
   if epoch!=1:rng.shuffle(ids)
   schedule.extend(ids)
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp);(d/'dut.sv').write_text((ROOT/'rtl/three_context_k7_coole_scheduled.sv').read_text().replace('module three_context_k7_coole_scheduled #(', 'module three_context_k7 #('))
   (d/'input.hex').write_text(''.join(f'{(a<<10)|(b<<2)|e:05x}\n' for ep in epochs for st in ep for a,b,e in st))
   (d/'schedule.hex').write_text(''.join(f'{c:x}\n' for c in schedule))
   (d/'tb.sv').write_text('''module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,sv=0,iv=0;reg[1:0]ctx=0,erase=0;reg[7:0]a=0,b=0;
wire sr,ir,ov,ob;wire[1:0]oc;
three_context_k7 dut(clk,resetn,sv,sr,ctx,oc,iv,ir,a,b,erase,ov,ob);
reg[17:0]words[0:18431];reg[1:0]order[0:18431];
integer e,j,c,k,index,t=0,f,g,h;integer count[0:2];reg[63:0]decision;integer committed;
task slot(input[1:0]who,input valid,input[17:0]word);
begin
 @(negedge clk);ctx=who;sv=1;iv=valid;{a,b,erase}=word;#1;
 if(!sr)$fatal(1,"slot not ready");
 if(valid&&!ir)$fatal(1,"input not ready");
 repeat(3)begin
 @(negedge clk);sv=1;ctx=3;iv=1;{a,b,erase}=18'h3ffff;
 if(sr)$fatal(1,"slot not atomic");
 end
 @(posedge clk);#2;sv=0;iv=0;t=t+1;
end endtask
initial begin
 $readmemh("input.hex",words);$readmemh("schedule.hex",order);
 f=$fopen("metrics.txt","w");g=$fopen("bits.txt","w");h=$fopen("events.txt","w");
 for(e=0;e<6;e=e+1)begin
 resetn=0;sv=0;iv=0;repeat(3)@(negedge clk);resetn=1;
 for(c=0;c<3;c=c+1)begin slot(c,0,0);count[c]=0;end
 for(j=0;j<3072;j=j+1)begin
 c=order[e*3072+j];index=e*3072+c*1024+count[c];
 slot(c,1,words[index]);count[c]=count[c]+1;
 if(j%37==0)slot((c+1)%3,0,0);
 if(j%79==0)repeat(7)@(negedge clk);
 end
 for(j=0;j<180;j=j+1)for(c=0;c<3;c=c+1)slot(c,0,0);
 // Enter a new four-clock job and reset before it retires. Old banks are dirty.
 @(negedge clk);ctx=e%3;sv=1;iv=1;a=77;b=201;erase=0;
 @(negedge clk);resetn=0;sv=0;iv=0;
 end
 $fclose(f);$fclose(g);$fclose(h);$finish;
end
always @(posedge clk)begin
 if(resetn&&dut.tick&&dut.initialized[dut.context_id]&&dut.step_enable&&dut.phase==3)begin
 committed=dut.context_id;decision={dut.lane_decision,dut.decision_partial};#1;
 $fwrite(f,"%0d %0d %x ",e,committed,decision);
 for(k=0;k<64;k=k+1)$fwrite(f,"%x ",dut.metrics[64*committed+k]);$fwrite(f,"\\n");end
end
always @(posedge clk)begin #1;if(resetn&&ov)$fdisplay(g,"%0d %0d %0d",e,oc,ob);end
always @(posedge clk) begin
 if(resetn && dut.tick && dut.start_trace) $fdisplay(h,"START %0d %0d",e,dut.context_id);
 if(resetn && dut.tick && dut.tracing[dut.context_id] && dut.walk[dut.context_id]==123 && (dut.phase==1 || dut.phase==3)) begin
   $fdisplay(h,"END %0d %0d",e,dut.context_id);
   if(dut.decoded_ready[dut.context_id][dut.decoded_write[dut.context_id]])
     $fdisplay(h,"OVERWRITE %0d %0d",e,dut.context_id);
 end
 if(resetn && dut.tick && dut.decoded_ready[dut.context_id][dut.decoded_read[dut.context_id]] &&
   dut.output_tick[dut.context_id] && dut.output_pos[dut.context_id]==63)
    $fdisplay(h,"DRAIN %0d %0d",e,dut.context_id);
end
endmodule''')
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(d/'sim'),str(d/'dut.sv'),str(d/'tb.sv')],check=True,capture_output=True)
   p=subprocess.run(['vvp',str(d/'sim')],cwd=d,check=True,capture_output=True,text=True,timeout=180)
   actual=[[[]for _ in range(3)]for _ in epochs];bits=[[[]for _ in range(3)]for _ in epochs]
   for line in (d/'metrics.txt').read_text().splitlines():
    ep,c,dec,*m=line.split();actual[int(ep)][int(c)].append(([int(v,16)for v in m],int(dec,16)))
   for line in (d/'bits.txt').read_text().splitlines():
    ep,c,b=map(int,line.split());bits[ep][c].append(b)
   from collections import Counter
   events=Counter()
   for event_row in (d/'events.txt').read_text().splitlines():
    event_kind,event_epoch,event_context=event_row.split()
    events[(event_kind,int(event_epoch),int(event_context))]+=1
  for ep in range(6):
   for c in range(3):
    with self.subTest(epoch=ep,context=c):
     self.assertEqual(actual[ep][c],oracle.reference(epochs[ep][c]))
     self.assertGreater(len(bits[ep][c]),800, f"epoch={ep} context={c}: count={len(bits[ep][c])}, trace starts={events[('START',ep,c)]}, trace completions={events[('END',ep,c)]}, overwrites={events[('OVERWRITE',ep,c)]}, drained={events[('DRAIN',ep,c)]}")
     if ep:
      observed=bits[ep][c][64:]
      expected=wanted[ep][c][64:len(bits[ep][c])]
      for offset,(bit_observed,reference) in enumerate(zip(observed,expected)):
       if bit_observed!=reference:
        self.fail(f"decoded-bit mismatch epoch={ep} context={c} bit={offset+64} actual={bit_observed} expected={reference} trace_starts={events[('START',ep,c)]} trace_completions={events[('END',ep,c)]} overwrites={events[('OVERWRITE',ep,c)]} drained={events[('DRAIN',ep,c)]}")
      self.assertEqual(len(observed),len(expected))

if __name__=='__main__':unittest.main()

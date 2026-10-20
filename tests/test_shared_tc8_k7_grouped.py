"""Prototype T3+TC8 shared ACS: unbounded metrics and coded+uncoded output oracle."""
import hashlib,json,math,os,random,shutil,subprocess,tempfile,unittest
from pathlib import Path
from experiments.shared_tc8_k7_context import generate
ROOT=Path(__file__).resolve().parents[1]
TB='module tb;\nreg clk=0;always #5 clk=~clk;\nreg resetn=0,sv=0,iv=0;reg[1:0]ctx=0,erase=0;reg[7:0]a=0,b=0;\nwire sr,ir,ov,ob;wire[1:0]oc;\nwire b1out;reg tc8=0;reg[35:0]costs=0;reg[3:0]choice=0;\nshared_tc8_k7_context dut(clk,resetn,sv,sr,ctx,oc,iv,ir,a,b,erase,ov,ob,tc8,costs,choice,b1out);\nreg[58:0]words[0:12287];reg[1:0]order[0:12287];\ninteger e,j,c,k,index,t=0,f,g;integer count[0:3];reg[63:0]decision;integer committed;\ntask slot(input[1:0]who,input valid,input[58:0]word);\nbegin\n @(negedge clk);ctx=who;sv=1;iv=valid;{tc8,costs,choice,a,b,erase}=word;#1;\n if(!sr)$fatal(1,"slot not ready");\n if(valid&&!ir)$fatal(1,"input not ready");\n @(negedge clk);sv=1;ctx=~who;iv=1;{tc8,costs,choice,a,b,erase}=59\'h7ffffffffffffff;\n if(sr)$fatal(1,"slot not atomic");\n @(posedge clk);#2;sv=0;iv=0;t=t+1;\nend endtask\ninitial begin\n $readmemh("input.hex",words);$readmemh("schedule.hex",order);\n f=$fopen("metrics.txt","w");g=$fopen("bits.txt","w");\n for(e=0;e<4;e=e+1)begin\n resetn=0;sv=0;iv=0;repeat(3)@(negedge clk);resetn=1;\n for(c=0;c<4;c=c+1)begin slot(c,0,0);count[c]=0;end\n for(j=0;j<3072;j=j+1)begin\n c=order[e*3072+j];index=e*3072+c*768+count[c];\n slot(c,1,words[index]);count[c]=count[c]+1;\n if(j%37==0)slot((c+1)%4,0,0);\n if(j%79==0)repeat(7)@(negedge clk);\n end\n for(j=0;j<180;j=j+1)for(c=0;c<4;c=c+1)slot(c,0,0);\n // Enter a new two-clock job and reset before it retires. Old banks are dirty.\n @(negedge clk);ctx=e==2?3:e%4;sv=1;iv=1;a=77;b=201;erase=0;\n @(negedge clk);resetn=0;sv=0;iv=0;\n end\n $fclose(f);$fclose(g);$finish;\nend\nalways @(posedge clk)begin\n if(resetn&&dut.tick&&dut.initialized[dut.context_id]&&dut.phase)begin\n committed=dut.context_id;decision={dut.lane_decision,dut.decision_partial};#1;\n $fwrite(f,"%0d %0d %x ",e,committed,decision);\n for(k=0;k<64;k=k+1)$fwrite(f,"%x ",dut.metrics[64*committed+k]);$fwrite(f,"\\n");end\nend\nalways @(posedge clk)begin #1;if(resetn&&ov)$fdisplay(g,"%0d %0d %0d %0d",e,oc,ob,b1out);end\nendmodule'

def branch_costs(i,q):
 # Independent max-dot-product constellation oracle, with the original quantizer.
 labels=(0,1,3,2,4,5,7,6)
 points={label:(round(32768*math.cos(k*math.pi/4)),round(32768*math.sin(k*math.pi/4)))for k,label in enumerate(labels)}
 scores=[];choice=0
 for xy in range(4):
  label=((xy&1)<<1)|(xy>>1)
  a,b=(i*points[label|(v<<2)][0]+q*points[label|(v<<2)][1]for v in (0,1))
  pick=int(b>a);choice|=pick<<xy;scores.append(max(a,b))
 peak=max(scores)
 return [min(511,(peak-x+(1<<21))>>22)for x in scores],choice

def reference(cost_rows):
 metrics=[0]*64;result=[]
 for costs in cost_rows:
  nxt=[];dec=0
  for state in range(64):
   candidates=[]
   for pred in (state//2,state//2+32):
    word=(pred<<1)|(state&1)
    label=((word&0o171).bit_count()%2)*2+((word&0o133).bit_count()%2)
    candidates.append(metrics[pred]+costs[label])
   nxt.append(min(candidates))
   if candidates[1]<candidates[0]:dec|=1<<state
  metrics=nxt;result.append(([v%8192 for v in metrics],dec))
 return result

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class SharedTC8Test(unittest.TestCase):
 def test_four_contexts_metrics_uncoded_bits_and_reset(self):
  rng=random.Random(190328);epochs=[];wanted=[];inputs=[];order=[];n=768
  points={label:(round(32768*math.cos(k*math.pi/4)),round(32768*math.sin(k*math.pi/4)))for k,label in enumerate((0,1,3,2,4,5,7,6))}
  for ep in range(4):
   rows4=[];bits4=[]
   for c in range(4):
    state=rng.randrange(64);rows=[];want=[]
    for j in range(n):
     if c<3 or ep==3:
      bit=rng.randrange(2);want.append(bit);state=((state<<1)|bit)&127
      if ep==0:a,b,er=rng.randrange(256),rng.randrange(256),rng.randrange(4)
      else:a,b=(230 if (state&g).bit_count()%2 else 25 for g in (0o171,0o133));er=0
      costs=[(0 if er&2 else 255-a if k&2 else a)+(0 if er&1 else 255-b if k&1 else b)for k in range(4)]
      word=(a<<10)|(b<<2)|er
     else:
      pair=rng.randrange(4);want.append(pair);state=((state<<1)|(pair&1))&127
      x=(state&0o171).bit_count()%2;y=(state&0o133).bit_count()%2
      pt=points[((pair>>1)<<2)|(y<<1)|x];amp=rng.uniform(.45,.8)
      i,q=(round(v*amp+rng.uniform(-600,600))for v in pt)
      costs,choice=branch_costs(i,q)
      word=(1<<58)|(sum(v<<(9*k)for k,v in enumerate(costs))<<22)|(choice<<18)
     inputs.append(word);rows.append(costs)
    rows4.append(rows);bits4.append(want)
   epochs.append(rows4);wanted.append(bits4)
   ids=[c for c in range(4)for _ in range(n)]
   if ep!=1:rng.shuffle(ids)
   order+=ids
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);generated=(ROOT/'experiments/shared_tc8_k7_grouped.sv').read_text()
   (p/'dut.sv').write_text(generated);(p/'tb.sv').write_text(TB)
   (p/'input.hex').write_text(''.join(f'{v:015x}\n'for v in inputs));(p/'schedule.hex').write_text(''.join(f'{v:x}\n'for v in order))
   r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'dut.sv'),str(p/'tb.sv')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run(['vvp',str(p/'sim')],cwd=d,capture_output=True,text=True,timeout=180)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   actual=[[[]for _ in range(4)]for _ in range(4)];bits=[[[]for _ in range(4)]for _ in range(4)]
   for line in (p/'metrics.txt').read_text().splitlines():
    ep,c,dec,*m=line.split();actual[int(ep)][int(c)].append(([int(v,16)for v in m],int(dec,16)))
   for line in (p/'bits.txt').read_text().splitlines():
    ep,c,b,b1=map(int,line.split());bits[ep][c].append((b1<<1|b)if c==3 and ep<3 else b)
   counts=[]
   for ep in range(4):
    for c in range(4):
     self.assertEqual(actual[ep][c],reference(epochs[ep][c]),f'ACS epoch {ep} context {c}')
     self.assertGreater(len(bits[ep][c]),n-256)
     if c==3 or ep:self.assertEqual(bits[ep][c][64:],wanted[ep][c][64:len(bits[ep][c])],f'output epoch {ep} context {c}')
    counts.append(list(map(len,bits[ep])))
  result=dict(scope=__doc__,epochs=4,symbols_per_context=n,state_checks=4*4*n*64,output_counts=counts,TC8_coded_and_uncoded_bits_verified=True,S_binary_epoch_verified=True,T_all_erasure_weights_verified=True,scheduler_FIFO_not_included=True,receiver_adopted=False,source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()for f in [Path(__file__),ROOT/'experiments/shared_tc8_k7_context.py',ROOT/'experiments/shared_tc8_k7_grouped.sv',ROOT/'rtl/shared_k7_context.sv']})
  print(json.dumps({k:v for k,v in result.items()if k!='source_sha256'}))
  if os.environ.get('SHARED_TC8_K7_REPORT'):Path(os.environ['SHARED_TC8_K7_REPORT']).write_text(json.dumps(result,indent=2)+'\n')

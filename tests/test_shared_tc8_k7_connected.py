"""Connected metric/depuncture/FIFO/scheduler/K7: independent full ACS and bit oracle."""
import json,hashlib,math,random,shutil,subprocess,tempfile,unittest
from pathlib import Path
from tests.test_shared_tc8_k7_context import branch_costs,reference
from tests.test_shared_k7_depuncture_stream import MASKS
ROOT=Path(__file__).resolve().parents[1]
FILES=['experiments/shared_tc8_k7_context.sv','experiments/shared_tc8_k7_stream.sv','experiments/shared_tc8_k7_depuncture_stream.sv','rtl/s3_depuncture.sv','rtl/s3_tc8psk_metric_folded.sv']
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ConnectedTest(unittest.TestCase):
 def test_all_rates_tc8_binary_backpressure_and_epochs(self):
  rng=random.Random(201026);n=768;epochs=[];wanted=[];inputs=[];orders=[];lengths=[];iq=[]
  points={label:(round(32768*math.cos(k*math.pi/4)),round(32768*math.sin(k*math.pi/4)))for k,label in enumerate((0,1,3,2,4,5,7,6))}
  for ep in range(6):
   rows4=[];bits4=[];ids=[]
   for c in range(4):
    state=rng.randrange(64);rows=[];bits=[];soft=[];mx,my=MASKS[(ep+c)%5]
    for j in range(n):
     value=rng.randrange(4) if c==3 and ep<5 else rng.randrange(2)
     state=((state<<1)|(value&1))&127;bits.append(value)
     x,y=((state&g).bit_count()%2 for g in (0o171,0o133))
     if c==3 and ep<5:
      pt=points[((value>>1)<<2)|(y<<1)|x];amp=rng.uniform(.45,.8)
      i,q=(round(v*amp+rng.uniform(-600,600))for v in pt)
      costs,_=branch_costs(i,q);iq.append(((i&65535)<<16)|(q&65535))
     else:
      a,b=230 if x else 25,230 if y else 25;er=0
      if mx[j%len(mx)]=='1':soft.append(a)
      else:a=0;er|=2
      if my[j%len(my)]=='1':soft.append(b)
      else:b=0;er|=1
      costs=[(0 if er&2 else 255-a if k&2 else a)+(0 if er&1 else 255-b if k&1 else b)for k in range(4)]
     rows.append(costs)
    inputs+=soft+[0]*(1536-len(soft));ids +=[c]*len(soft);rows4.append(rows);bits4.append(bits)
   rng.shuffle(ids);lengths.append(len(ids));orders+=ids+[0]*(6144-len(ids));epochs.append(rows4);wanted.append(bits4)
  with tempfile.TemporaryDirectory() as temp:
   d=Path(temp)
   for name,values,width in [('soft',inputs,2),('order',orders,1),('iq',iq,8)]:
    (d/(name+'.hex')).write_text(''.join(f'{x:0{width}x}\n'for x in values))
   tb=TB.replace('LENGTH_INIT',''.join(f'lengths[{e}]={v};'for e,v in enumerate(lengths)))
   (d/'tb.sv').write_text(tb)
   p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(d/'sim'),*[str(ROOT/f)for f in FILES],str(d/'tb.sv')],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stderr)
   p=subprocess.run(['vvp',str(d/'sim')],cwd=d,capture_output=True,text=True,timeout=240)
   self.assertEqual(p.returncode,0,p.stdout+p.stderr)
   actual=[[[]for _ in range(4)]for _ in epochs];bits=[[[]for _ in range(4)]for _ in epochs]
   for line in (d/'metrics.txt').read_text().splitlines():
    e,c,dec,*m=line.split();actual[int(e)][int(c)].append(([int(x,16)for x in m],int(dec,16)))
   for line in (d/'bits.txt').read_text().splitlines():
    e,c,b,b1,mode=map(int,line.split());self.assertEqual(mode,int(c==3 and e<5));bits[e][c].append((b1<<1|b)if mode else b)
   stats=json.loads((d/'stats.json').read_text())
  counts=[]
  for ep in range(6):
   for c in range(4):
    self.assertEqual(actual[ep][c],reference(epochs[ep][c]),f'ACS epoch {ep} ctx {c}')
    self.assertEqual(len(bits[ep][c]),704)
    self.assertEqual(bits[ep][c][64:],wanted[ep][c][64:704],f'bits epoch {ep} ctx {c}')
    counts.append(len(bits[ep][c]))
  self.assertGreater(stats['iq_stalls'],0);self.assertGreater(stats['soft_stalls'],0)
  report=dict(scope=__doc__,passed=True,epochs=6,steps_per_context=n,ACS_states=6*4*n*64,output_counts=counts,**stats,whole_receiver_verified=False,real_time_deadlines_verified=False,source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in FILES})
  (ROOT/'reports/shared-tc8-k7-connected-test.json').write_text(json.dumps(report,indent=2)+'\n')
TB=r'''module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0,iv=0,qv=0,mode=0;reg[11:0]rates=0;reg[1:0]ctx=0;reg[7:0]llr=0;reg signed[15:0]ii=0,qq=0;
wire ir,qr,ov,ob,b1,ot;wire[1:0]oc;wire[3:0]fault;
shared_tc8_k7_depuncture_stream dut(.clk(clk),.resetn(rst),.rates(rates),.s_tc8_mode(mode),.iq_valid(qv),.iq_ready(qr),.in_i(ii),.in_q(qq),.out_b1(b1),.out_tc8(ot),.in_valid(iv),.in_ready(ir),.in_context(ctx),.in_soft(llr),.out_valid(ov),.out_bit(ob),.out_context(oc),.fault(fault));
reg[7:0]words[0:36863];reg[1:0]order[0:36863];reg[31:0]iq[0:3839];
integer lengths[0:5];integer count[0:3];integer ep,j,c,k,z,f,g,h,who,ss=0,qs=0,t=0;reg observe=0;reg[63:0]decision;
initial begin
 LENGTH_INIT
 $readmemh("soft.hex",words);$readmemh("order.hex",order);$readmemh("iq.hex",iq);
 f=$fopen("metrics.txt","w");g=$fopen("bits.txt","w");
 for(ep=0;ep<6;ep=ep+1)begin
  rst=0;observe=0;iv=0;qv=0;mode=ep<5;
  for(c=0;c<4;c=c+1)begin rates[3*c+:3]=(ep+c)%5;count[c]=0;end
  repeat(3)@(negedge clk);rst=1;observe=1;repeat(2)@(negedge clk);
  fork
   begin
    for(j=0;j<lengths[ep];j=j+1)begin
     @(negedge clk);c=order[ep*6144+j];ctx=c;llr=words[ep*6144+1536*c+count[c]];iv=1;
     @(posedge clk);while(!ir)begin ss=ss+1;@(posedge clk);end
     count[c]=count[c]+1;
     if(j%113==0)begin @(negedge clk);iv=0;repeat(11)@(negedge clk);end
    end
    @(negedge clk);iv=0;
   end
   begin
    if(ep<5)for(z=0;z<768;z=z+1)begin
     @(negedge clk);{ii,qq}=iq[ep*768+z];qv=1;
     @(posedge clk);while(!qr)begin qs=qs+1;@(posedge clk);end
    end
    @(negedge clk);qv=0;
   end
  join
  repeat(2000)@(negedge clk);observe=0;
  // Mode cannot change during an epoch. Sticky fault must reset cleanly.
  mode=!mode;repeat(3)@(negedge clk);
  if(!fault[3]||ir||qr)$fatal(1,"illegal live mode switch not blocked");
  rst=0;
 end
 h=$fopen("stats.json","w");$fdisplay(h,"{\"soft_stalls\":%0d,\"iq_stalls\":%0d,\"cycles\":%0d}",ss,qs,t);$fclose(h);
 $fclose(f);$fclose(g);$finish;
end
always @(posedge clk)begin
 t=t+1;if(t>250000)$fatal(1,"timeout");
 if(observe&&rst&&fault)$fatal(1,"unexpected fault");
 if(observe&&rst&&dut.stream.core.tick&&dut.stream.core.initialized[dut.stream.core.context_id]&&dut.stream.core.phase)begin
  who=dut.stream.core.context_id;decision={dut.stream.core.lane_decision,dut.stream.core.decision_partial};#1;
  $fwrite(f,"%0d %0d %x ",ep,who,decision);
  for(k=0;k<64;k=k+1)$fwrite(f,"%x ",dut.stream.core.metrics[64*who+k]);$fwrite(f,"\n");
 end
end
always @(posedge clk)begin #1;if(observe&&rst&&ov)$fdisplay(g,"%0d %0d %0d %0d %0d",ep,oc,ob,b1,ot);end
endmodule'''
if __name__=='__main__':unittest.main()

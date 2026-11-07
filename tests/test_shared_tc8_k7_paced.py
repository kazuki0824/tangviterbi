"""Finite ideal-source deadline probe, not actual SDRAM service or full S burst proof."""
import hashlib,json,math,random,shutil,subprocess,tempfile,unittest
from pathlib import Path
from tests.test_shared_tc8_k7_connected import FILES,ROOT
from tests.test_shared_k7_depuncture_stream import MASKS
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class PacedTest(unittest.TestCase):
 def test_mode1_t_three_layers_and_s_tc8_or_binary(self):
  rng=random.Random(201027);nclock=80190;per=[576,2880,4032];steps=[1008,5040,7056]
  s_bytes=29992;s_tc=14999;s_steps=s_bytes//8*7
  all_soft=[];all_iq=[];wanted=[]
  points={label:(round(32768*math.cos(k*math.pi/4)),round(32768*math.sin(k*math.pi/4)))for k,label in enumerate((0,1,3,2,4,5,7,6))}
  for ep in range(2):
   expected=[]
   for c in range(4):
    n=steps[c]if c<3 else s_tc if ep==0 else s_steps
    state=rng.randrange(64);bits=[];values=[];mx,my=MASKS[4]
    for j in range(n):
     value=rng.randrange(4)if ep==0 and c==3 else rng.randrange(2);bits.append(value)
     state=((state<<1)|(value&1))&127;x,y=((state&g).bit_count()%2 for g in (0o171,0o133))
     if ep==0 and c==3:
      p=points[((value>>1)<<2)|(y<<1)|x];amp=rng.uniform(.5,.8)
      i,q=(round(v*amp+rng.uniform(-400,400))for v in p);all_iq.append(((i&65535)<<16)|(q&65535))
     else:
      if mx[j%7]=='1':values.append(230 if x else 25)
      if my[j%7]=='1':values.append(230 if y else 25)
    all_soft+=values+[0]*(32768-len(values));expected.append(bits)
   wanted.append(expected)
  with tempfile.TemporaryDirectory() as temp:
   d=Path(temp)
   (d/'soft.hex').write_text(''.join(f'{x:02x}\n'for x in all_soft));(d/'iq.hex').write_text(''.join(f'{x:08x}\n'for x in all_iq));(d/'tb.sv').write_text(TB)
   p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(d/'sim'),*[str(ROOT/f)for f in FILES],str(d/'tb.sv')],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
   p=subprocess.run(['vvp',str(d/'sim')],cwd=d,capture_output=True,text=True,timeout=240);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
   bits=[[[]for c in range(4)]for ep in range(2)]
   for line in (d/'bits.txt').read_text().splitlines():
    ep,c,b,b1=map(int,line.split());bits[ep][c].append((b1<<1|b)if ep==0 and c==3 else b)
   records=[json.loads(line)for line in (d/'stats.jsonl').read_text().splitlines()]
  for ep in range(2):
   for c in range(4):
    self.assertEqual(len(bits[ep][c]),(len(wanted[ep][c])//64-1)*64)
    self.assertEqual(bits[ep][c][64:],wanted[ep][c][64:len(bits[ep][c])],f'{ep}/{c}')
   self.assertLess(records[ep]['T_max_symbol_ACS_latency_clocks'],40095)
  report=dict(scope=__doc__,passed=True,clock_MHz=1080/7,T_mode=1,T_segments=[1,5,7],T_rate='7/8',T_symbols=2,T_symbol_clocks=40095,T_soft_MBps=7488/40095*(1080/7),S_tc8_Msymbolps=28.86,S_binary_soft_MBps=57.72,S_source_queue_capacity=256,source_queues_in_testbench_only=True,actual_SDRAM_service_connected=False,S_arrival_uniform_not_actual_burst=True,all_phase_or_long_term_proof=False,records=records,output_counts=[[len(x) for x in row] for row in bits],output_bank_granularity=64,source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in FILES+['tests/test_shared_tc8_k7_paced.py']})
  (ROOT/'reports/shared-tc8-k7-paced-test.json').write_text(json.dumps(report,indent=2)+'\n')
TB=r'''module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0,iv=0,qv=0,mode=0;reg[1:0]ctx=0;reg[7:0]llr=0;reg signed[15:0]ii=0,qq=0;
wire ir,qr,ov,ob,b1,ot;wire[1:0]oc;wire[3:0]fault;
shared_tc8_k7_depuncture_stream dut(.clk(clk),.resetn(rst),.rates(12'h924),.s_tc8_mode(mode),.iq_valid(qv),.iq_ready(qr),.in_i(ii),.in_q(qq),.out_b1(b1),.out_tc8(ot),.in_valid(iv),.in_ready(ir),.in_context(ctx),.in_soft(llr),.out_valid(ov),.out_bit(ob),.out_context(oc),.fault(fault));
reg[7:0]words[0:262143];reg[31:0]iq[0:14998];
integer ep,t,c,j,k,sel,rr,scount,qcount,avail,phase,peak,delay,maxdelay,who,f,g;
integer count[0:3];integer done[0:3];integer per[0:2];integer step_per[0:2];integer peak_fifo[0:3];integer s_last,s_gap,s_maxgap;
reg observe=0;
initial begin
 $readmemh("soft.hex",words);$readmemh("iq.hex",iq);
 f=$fopen("bits.txt","w");g=$fopen("stats.jsonl","w");
 per[0]=576;per[1]=2880;per[2]=4032;step_per[0]=504;step_per[1]=2520;step_per[2]=3528;
 for(ep=0;ep<2;ep=ep+1)begin
  rst=0;iv=0;qv=0;observe=0;mode=ep==0;
  rr=0;scount=0;qcount=0;phase=0;peak=0;maxdelay=0;s_last=0;s_maxgap=0;
  for(c=0;c<4;c=c+1)begin count[c]=0;done[c]=0;peak_fifo[c]=0;end
  repeat(3)@(negedge clk);rst=1;repeat(2)@(negedge clk);observe=1;
  for(t=0;t<83000;t=t+1)begin
   // Finite source: T symbol data is available in full at symbol release.
   // S is uniform. These queues/selector are a TB source, not charged RTL.
   if(t<80190)begin
    phase=phase+(ep==0?3367:6734);
    if(phase>=18000)begin phase=phase-18000;if(scount<(ep==0?14999:29992))scount=scount+1;end
   end
   avail=scount-(ep==0?qcount:count[3]);if(avail>peak)peak=avail;
   if(avail>256)$fatal(1,"S source queue overflow");
   sel=-1;
   for(j=0;j<4;j=j+1)begin
    k=(rr+j)%4;
    if(k<3)begin avail=(t<40095?per[k]:2*per[k])-count[k];end
    else avail=ep==1?scount-count[3]:0;
    if(sel<0 && avail>0 && dut.soft_ready[k])sel=k;
   end
   iv=sel>=0;
   if(iv)begin ctx=sel;llr=words[ep*131072+sel*32768+count[sel]];end
   qv=ep==0 && qcount<scount;
   if(qv){ii,qq}=iq[qcount];
   @(posedge clk);
   if(iv&&ir)begin count[sel]=count[sel]+1;rr=(sel+1)%4;end
   if(qv&&qr)qcount=qcount+1;
   @(negedge clk);
  end
  iv=0;qv=0;observe=0;
  for(c=0;c<3;c=c+1)if(done[c]!=2*step_per[c] || count[c]!=2*per[c])$fatal(1,"T incomplete");
  if(ep==0 && (qcount!=14999 || done[3]!=14999))$fatal(1,"TC8 incomplete");
  if(ep==1 && (count[3]!=29992 || done[3]!=26243))$fatal(1,"binary incomplete");
  $fdisplay(g,"{""epoch"":%0d,""TC8"":%0d,""S_source_queue_peak"":%0d,""T_max_symbol_ACS_latency_clocks"":%0d,""S_max_ACS_gap_clocks"":%0d,""FIFO_peak"":[%0d,%0d,%0d,%0d]}",ep,ep==0,peak,maxdelay,s_maxgap,peak_fifo[0],peak_fifo[1],peak_fifo[2],peak_fifo[3]);
 end
 $fclose(f);$fclose(g);$finish;
end
always @(posedge clk)begin
 if(observe&&rst)begin
  if(fault)$fatal(1,"fault");
  if(dut.stream.g_fifo[0].count>peak_fifo[0])peak_fifo[0]=dut.stream.g_fifo[0].count;
  if(dut.stream.g_fifo[1].count>peak_fifo[1])peak_fifo[1]=dut.stream.g_fifo[1].count;
  if(dut.stream.g_fifo[2].count>peak_fifo[2])peak_fifo[2]=dut.stream.g_fifo[2].count;
  if(dut.stream.g_fifo[3].count>peak_fifo[3])peak_fifo[3]=dut.stream.g_fifo[3].count;
  if(dut.stream.core.tick&&dut.stream.core.initialized[dut.stream.core.context_id]&&dut.stream.core.phase)begin
   who=dut.stream.core.context_id;done[who]=done[who]+1;
   if(who<3 && done[who]%step_per[who]==0)begin
    delay=t-(done[who]/step_per[who]-1)*40095;
    if(delay>maxdelay)maxdelay=delay;
   end
   if(who==3)begin
    if(done[3]>1 && t-s_last>s_maxgap)s_maxgap=t-s_last;
    s_last=t;
   end
  end
 end
end
always @(posedge clk)begin #1;if(observe&&rst&&ov)$fdisplay(f,"%0d %0d %0d %0d",ep,oc,ob,b1);end
endmodule'''
# Keep Verilog JSON string escapes visible in the raw literal above.
TB=TB.replace('""','\\"')
if __name__=='__main__':unittest.main()

"""Joint service/reader + real shared K7, S FIFO and pin-level SDRAM oracle.
Synthetic periodic BG/FFT sources; not real FFT/interleavers, PHY or RF-to-TS.
"""
import hashlib,json,math,random,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
from tests.test_shared_tc8_k7_connected import FILES as KFILES,ROOT
FILES=['rtl/sdf_delay_cache.sv','rtl/sdram_client_arbiter.sv','rtl/dual_sdram_burst.sv','rtl/sdf_sdram_service.sv','rtl/t_soft_reader.sv','rtl/t_soft_sdram_service.sv',*KFILES,'experiments/s_input_fifo.sv','experiments/shared_receiver_service.sv','experiments/t_soft_reader_buffered.sv','experiments/t_soft_sdram_service_buffered.sv','experiments/shared_receiver_service_buffered.sv','experiments/shared_receiver_service_elastic.sv']
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ElasticJointTest(unittest.TestCase):
 def test_real_memory_contention_binary_and_tc8(self):
  rng=random.Random(201029);words=[];expected_t=[]
  for per in [576,2880,4032]:
   n=3*per*7//8;state=0;bits=[];soft=[]
   for j in range(n):
    b=rng.randrange(2);bits.append(b);state=((state<<1)|b)&127
    for g,mask in [(0o171,'1000101'),(0o133,'1111010')]:
     if mask[j%7]=='1':soft.append(230 if (state&g).bit_count()%2 else 25)
   self.assertEqual(len(soft),3*per);words+=soft;expected_t.append(bits)
  state=0;sbits=[];ssoft=[]
  for j in range(29992*7//8):
   b=rng.randrange(2);sbits.append(b);state=((state<<1)|b)&127
   for g,mask in [(0o171,'1000101'),(0o133,'1111010')]:
    if mask[j%7]=='1':ssoft.append(230 if (state&g).bit_count()%2 else 25)
  words+=ssoft;iqs=[];tbits=[];state=0
  points={label:(round(32768*math.cos(k*math.pi/4)),round(32768*math.sin(k*math.pi/4)))for k,label in enumerate((0,1,3,2,4,5,7,6))}
  for j in range(14999):
   pair=rng.randrange(4);tbits.append(pair);state=((state<<1)|(pair&1))&127
   x,y=((state&g).bit_count()%2 for g in [0o171,0o133]);point=points[((pair>>1)<<2)|(y<<1)|x]
   amp=rng.uniform(.5,.8);i,q=(round(v*amp+rng.uniform(-400,400))for v in point);iqs.append(((i&65535)<<16)|(q&65535))
  traces=[]
  with tempfile.TemporaryDirectory() as temp:
   d=Path(temp);(d/'soft.hex').write_text(''.join(f'{v:02x}\n'for v in words));(d/'iq.hex').write_text(''.join(f'{v:08x}\n'for v in iqs));(d/'tb.sv').write_text(TB)
   for variant,tc8 in [(2,t)for t in [0,1]]:
    with self.subTest(buffered=variant,TC8=tc8):
     (d/'tb.sv').write_text(TB.replace('shared_receiver_service dut','shared_receiver_service_elastic dut')if variant else TB)
     p=subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.TC8={tc8}','-o',str(d/'sim'),*[str(ROOT/f)for f in FILES],str(d/'tb.sv')],text=True,capture_output=True);self.assertEqual(p.returncode,0,p.stderr)
     p=subprocess.run(['vvp',str(d/'sim')],cwd=d,text=True,capture_output=True,timeout=300);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
     bits=[[]for c in range(4)]
     for line in (d/'bits.txt').read_text().splitlines():
      c,b,b1=line.split();c=int(c);bits[c].append(int(b1)<<1|int(b) if tc8 and c==3 else int(b))
     for c in range(4):
      expected=expected_t[c] if c<3 else tbits if tc8 else sbits
      n=[1008,5040,7056,14999 if tc8 else 26243][c]
      self.assertEqual(len(bits[c]),(n//64-1)*64)
      self.assertEqual(bits[c][64:],expected[64:len(bits[c])],f'TC8={tc8} context={c}')
     result={k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',p.stdout)};result['TC8']=tc8;result['buffered_response']=bool(variant);result['outputs']=[len(x)for x in bits];traces.append(result);print(p.stdout,flush=True)
  report=dict(scope=__doc__,passed_functional_and_data=True,clock_MHz=1080/7,T_mode=1,T_segments=[1,5,7],T_rate='7/8',period_clocks=40095,periods=2,initial_T_symbol_prefill_before_start=True,T_writes_complete_before_commit=True,real_controller_reader_K7_and_S_FIFO=True,external_BG_request_holding_in_TB=True,actual_S_interleaver_burst=False,S_uniform_arrival=True,whole_receiver_verified=False,all_phase_or_long_term_proof=False,traces=traces,all_diagnostic_deadlines_pass=all(t['deadline_misses']==0 for t in traces),source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest()for f in FILES+['tests/test_shared_receiver_service_elastic.py']})
  (ROOT/'reports/shared-receiver-service-elastic-test.json').write_text(json.dumps(report,indent=2)+'\n')
TB=r'''module tb;
parameter TC8=0;
reg clk=0;always #5 clk=~clk;
reg rst=0,cv=0,take=0,re=0,we=0,svalid=0;reg[62:0]ca=0;reg[31:0]sdata=0;
reg[11:0]ra=0,wa=0,held=0;reg[31:0]wd=0;
reg[3:0]v=0,w=0;reg[83:0]a=0;reg[1023:0]data=0;reg[127:0]mask=0;
wire er,cr,reuse,init,fault,sready,ov,ob,b1,ot,cke,oe;wire[1:0]live,oc,bank;wire[2:0]cmd;wire[10:0]sa;wire[3:0]br,bv,dqm;wire[255:0]bd;wire[31:0]rdata,dq;reg[31:0]din=0;
shared_receiver_service dut(.clk(clk),.resetn(rst),.sample_accept(take),.external_ready(er),.read_enable(re),.read_address(ra),.read_data(rdata),.write_enable(we),.write_address(wa),.write_data(wd),.bg_valid(v),.bg_ready(br),.bg_write(w),.bg_address(a),.bg_data(data),.bg_dqm(mask),.bg_rsp_valid(bv),.bg_rsp_ready(4'b1111),.bg_rsp_data(bd),.commit_valid(cv),.commit_ready(cr),.commit_addresses(ca),.commit_lengths({16'd4032,16'd2880,16'd576}),.bank_live(live),.reuse_blocked(reuse),.rates(12'h924),.s_tc8_mode(TC8!=0),.s_valid(svalid),.s_ready(sready),.s_data(sdata),.out_valid(ov),.out_bit(ob),.out_b1(b1),.out_tc8(ot),.out_context(oc),.initialized(init),.fault(fault),.sd_cmd(cmd),.sd_bank(bank),.sd_address(sa),.sd_cke(cke),.sd_dqm(dqm),.dq_oe(oe),.dq_out(dq),.dq_in(din));
reg[7:0]soft_words[0:52455];reg[31:0]iq[0:14998];reg[31:0]mem[0:131071];
integer rows[0:3],activated[0:3],precharged[0:3],lastwrite[0:3];reg[3:0]opened=0;
integer cycle=0,read_at=-10000,read_base=0,wleft=0,waddr=0,wbank=0,base,j,refs=0,lastref=-10000,maxref=0,mode_at=-10000;
integer start=-1,commits=0,periods=0,target[0:3],done[0:3],i,k,sym,boff,coff;
integer read_due=-1,write_due=-1,next_sample=0,samples=0,available_s=0,consumed_s=0,acc=0,speak=0,fifo_peak=0,source_backlog=0;
integer step[0:3],per_step[0:2],got[0:2],offsets[0:2],bytes_per[0:2],max_t_delay=0,delay_now,deadline_misses=0,fft_first=-1,write_B=-1,write_C=-1,commit_lateness=0,writer_reuse_wait=0;
integer all_done=-1,fft_done=-1,f,read_requests=0,t_writes=0;reg[3:0]waiting=0;
function[7:0]tbyte(input integer symbol,input integer offset);
 integer c,o;
 begin
  if(offset<576)begin c=0;o=offset;end
  else if(offset<3456)begin c=1;o=offset-576;end
  else begin c=2;o=offset-3456;end
  tbyte=soft_words[offsets[c]+symbol*bytes_per[c]+o];
 end
endfunction
always @(negedge clk)begin
 if(cycle+1>=read_at && cycle+1<read_at+8)din=mem[read_base+cycle+1-read_at];else din=0;
 if(rst)begin
  // Initial T symbol is written through the actual controller before t=0.
  // Thereafter one next-symbol write set arrives each nominal period.
  if(start<0 && done[0]==234 && er && commits==0)begin cv=1;ca={21'd9056,21'd8336,21'd8192};end
  else if(start>=0 && cycle+1-start>=40095 && done[0]>=468 && commits==1)begin cv=1;ca={21'd11104,21'd10384,21'd10240};end
  else cv=0;
  take=start>=0 && samples<(periods*2048) && cycle>=next_sample && er;
  re=cycle+1==read_due;ra=held;we=cycle+1==write_due;wa=held;wd=32'h81230000+samples;
  if(!svalid)begin
   svalid=consumed_s<available_s;
   if(svalid)sdata=TC8?iq[consumed_s]:{24'd0,soft_words[22464+consumed_s]};
  end
  for(i=0;i<4;i=i+1)if(!v[i]&&!waiting[i]&&done[i]<target[i] && (i!=0 || done[0]<468 || !live[0]))begin
   v[i]=1;
   if(i==0)begin
    sym=done[0]/234;boff=(done[0]%234)*32;
    a[20:0]=(sym==1?10240:8192)+(done[0]%234)*8;w[0]=1;
    for(k=0;k<32;k=k+1)data[k*8+:8]=tbyte(sym,boff+k);
   end else begin
    a[21*i+:21]=21'h10000+i*21'h4000+(done[i]%128)*8;
    w[i]=done[i]%2==0;
    for(k=0;k<8;k=k+1)data[256*i+32*k+:32]=32'h69000000+(i<<20)+(done[i]<<3)+k;
    mask[32*i+:32]=done[i]*32'h78113205;
   end
  end
 end
end
always @(posedge clk)begin
 cycle=cycle+1;
 if(cycle%10000==0)$display("PROGRESS cycle=%0d start=%0d T_write=%0d commits=%0d S=%0d steps=%0d/%0d/%0d/%0d",cycle,start,done[0],commits,consumed_s,step[0],step[1],step[2],step[3]);
 if(rst)begin
  if(fault)$fatal(1,"joint fault cycle %0d",cycle);
  // Independent SDRAM command decoder and declared-cycle timing checks.
  if(wleft>0)begin
   if(!oe)$fatal(1,"write burst hole");
   for(j=0;j<4;j=j+1)if(!dqm[j])mem[waddr][8*j+:8]=dq[8*j+:8];
   wleft=wleft-1;waddr=waddr+1;lastwrite[wbank]=cycle;
  end
  if(cycle>=read_at&&cycle<read_at+8&&oe)$fatal(1,"DQ collision");
  if(cmd!=7&&cycle-lastref<12)$fatal(1,"tRFC");
  case(cmd)
   0:begin if(refs<8||sa!=11'h33||bank!=0)$fatal(1,"mode");mode_at=cycle;end
   1:begin
    if(opened)$fatal(1,"refresh open");
    if(refs>=9&&cycle-lastref>1203)$fatal(1,"refresh deadline");
    if(refs>=8&&cycle-lastref>maxref)maxref=cycle-lastref;
    refs=refs+1;lastref=cycle;
   end
   2:for(j=0;j<4;j=j+1)if(sa[10]||j==bank)begin
    if(opened[j]&&(cycle-activated[j]<6||cycle-lastwrite[j]<4))$fatal(1,"tRAS/tWR");
    opened[j]=0;precharged[j]=cycle;
   end
   3:begin
    if(opened[bank]||cycle-precharged[bank]<4||cycle-mode_at<4)$fatal(1,"activate");
    opened[bank]=1;rows[bank]=sa;activated[bank]=cycle;
   end
   4,5:begin
    if(!opened[bank]||cycle-activated[bank]<4||sa[10])$fatal(1,"column");
    base=(rows[bank]*4+bank)*256+sa[7:0];if(base+7>=131072)$fatal(1,"range");
    if(cmd==4)begin
     if(!oe)$fatal(1,"first write");
     for(j=0;j<4;j=j+1)if(!dqm[j])mem[base][8*j+:8]=dq[8*j+:8];
     lastwrite[bank]=cycle;wleft=7;waddr=base+1;wbank=bank;
    end else begin read_base=base;read_at=cycle+3;end
   end
  endcase
  if(cv&&cr)begin
   commits=commits+1;
   if(start<0)begin start=cycle;next_sample=cycle+1;periods=1;target[0]=468;target[1]=523;target[2]=186;target[3]=82;end
   else begin commit_lateness=cycle-start-40095;if(commit_lateness>0)deadline_misses=deadline_misses+1;end
  end
  if(start>=0)begin
   if(cycle-start==40095)begin periods=2;target[0]=702;target[1]=1046;target[2]=372;target[3]=164;end
   if(samples==2048 && cycle>write_due && dut.memory.service.cache.state==2 && dut.memory.service.cache.word_index==0 && !dut.memory.service.cache.pending && fft_first<0)fft_first=cycle-start;
   if(take&&er)begin read_due=cycle+1;write_due=cycle+6;held=samples%4096;samples=samples+1;next_sample=cycle+13;end
   if(cycle-start<80190 && available_s<(TC8?14999:29992))begin
    acc=acc+(TC8?3367:6734);
    if(acc>=18000)begin acc=acc-18000;available_s=available_s+1;end
   end
   if(svalid&&sready)begin consumed_s=consumed_s+1;svalid<=0;end
   if(available_s-consumed_s>speak)speak=available_s-consumed_s;
   if(available_s-consumed_s>256)$fatal(1,"external S source backlog >256");
   if(dut.s_fifo.count+dut.s_fifo.out_valid>fifo_peak)fifo_peak=dut.s_fifo.count+dut.s_fifo.out_valid;
   if(done[0]>=468 && done[0]<702 && live[0])writer_reuse_wait=writer_reuse_wait+1;
   if(dut.memory.reader.req_valid&&dut.memory.reader.req_ready)read_requests=read_requests+1;
   if(dut.tv&&dut.tr)begin
    if(dut.td!==soft_words[offsets[dut.tc]+got[dut.tc]])$fatal(1,"T data mismatch context=%0d byte=%0d",dut.tc,got[dut.tc]);
    got[dut.tc]=got[dut.tc]+1;
   end
   if(dut.k7.stream.core.tick&&dut.k7.stream.core.initialized[dut.k7.stream.core.context_id]&&dut.k7.stream.core.phase)begin
    j=dut.k7.stream.core.context_id;step[j]=step[j]+1;
    if(j<3 && step[j]%per_step[j]==0)begin
     delay_now=cycle-start-(step[j]/per_step[j]-1)*40095;
     if(delay_now>max_t_delay)max_t_delay=delay_now;
     if(delay_now>40095)deadline_misses=deadline_misses+1;
    end
   end
   if(samples==4096&&cycle>write_due&&dut.memory.service.cache.state==2&&dut.memory.service.cache.word_index==0&&!dut.memory.service.cache.pending&&fft_done<0)fft_done=cycle-start;
   if(commits==2 && step[0]==1008&&step[1]==5040&&step[2]==7056&&step[3]==(TC8?14999:26243)&&fft_done>=0&&done[0]==702&&done[1]==1046&&done[2]==372&&done[3]==164&&all_done<0)all_done=cycle-start;
  end
  for(i=0;i<4;i=i+1)begin
   if(v[i]&&br[i])begin v[i]<=0;waiting[i]<=1;end
   if(bv[i])begin waiting[i]<=0;done[i]=done[i]+1;
    if(i==0 && done[0]==468)write_B=cycle-start;
    if(i==0 && done[0]==702)write_C=cycle-start;
   end
  end
 end
 #1;if(start>=0&&ov)$fdisplay(f,"%0d %0d %0d",oc,ob,b1);
 if(all_done>=0 && cycle-start>=all_done+2000)begin
  if(read_requests!=468||live)$fatal(1,"T requests/live");
  if(fft_first>40095)deadline_misses=deadline_misses+1;
  if(fft_done>80190)deadline_misses=deadline_misses+1;
  if(write_B>40095)deadline_misses=deadline_misses+1;
  if(write_C>80190)deadline_misses=deadline_misses+1;
  $display("RESULT max_T_symbol_ACS_latency=%0d deadline_misses=%0d commit_lateness=%0d S_external_backlog_peak=%0d S_FIFO_peak=%0d writer_reuse_wait=%0d all_done=%0d FFT_done=%0d FFT_first=%0d write_B=%0d write_C=%0d read_requests=%0d T_writes=%0d refreshes=%0d max_refresh_gap=%0d",max_t_delay,deadline_misses,commit_lateness,speak,fifo_peak,writer_reuse_wait,all_done,fft_done,fft_first,write_B,write_C,read_requests,done[0],refs,maxref);
  $fclose(f);$finish;
 end
 if(cycle>300000)$fatal(1,"timeout start=%0d commit=%0d S=%0d/%0d steps=%0d/%0d/%0d/%0d BG=%0d/%0d/%0d/%0d samples=%0d",start,commits,consumed_s,available_s,step[0],step[1],step[2],step[3],done[0],done[1],done[2],done[3],samples);
end
initial begin
 $readmemh("soft.hex",soft_words);$readmemh("iq.hex",iq);f=$fopen("bits.txt","w");
 offsets[0]=0;offsets[1]=1728;offsets[2]=10368;bytes_per[0]=576;bytes_per[1]=2880;bytes_per[2]=4032;
 per_step[0]=504;per_step[1]=2520;per_step[2]=3528;
 for(i=0;i<4;i=i+1)begin target[i]=0;done[i]=0;step[i]=0;rows[i]=0;activated[i]=-10000;precharged[i]=-10000;lastwrite[i]=-10000;end
 for(i=0;i<3;i=i+1)got[i]=0;
 for(i=0;i<131072;i=i+1)mem[i]=0;
 target[0]=234;repeat(3)@(negedge clk);rst=1;
end
endmodule'''
if __name__=='__main__':unittest.main()

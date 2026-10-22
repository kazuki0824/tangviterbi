"""Finite contention diagnostic: real service/cache, synthetic stage traffic, ideal T sink.
No FFT arithmetic, K7, independent SDRAM data oracle or physical memory model.
"""
import hashlib,json,os,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TB=r'''
module tb;
parameter FFT_PHASE=0;
reg clk=0;always #5 clk=~clk;
reg resetn=0,commit=0;wire commit_ready;wire[1:0]live;wire reuse,qv,rr,sv,rf;
wire[20:0]qa;wire[1:0]sc;wire[7:0]sd;
wire[4:0]br,bv;wire[255:0]bd;
t_soft_reader reader(clk,resetn,commit,commit_ready,{21'd12800,21'd10496,21'd8192},
 {16'd11520,16'd9216,16'd9216},live,reuse,qv,br[1],qa,bv[1],rr,bd,sv,1'b1,sc,sd,rf);
// Sizes total 29952 B. Addresses are disjoint aligned word regions.
reg[4:0]v=0,w=0;reg[104:0]a=0;reg[1279:0]data=0;reg[159:0]mask=0;
wire[4:0]valid={v[4:2],qv,v[0]};wire[104:0]addr={a[104:42],qa,a[20:0]};
wire[4:0]rsp_ready={3'b111,rr,1'b1};
reg take=0,re=0,we=0;reg[11:0]ra=0,wa=0,held=0;reg[31:0]wd=0;
wire er,initialized,sf;wire[31:0]rdata,dq;wire[2:0]cmd;wire[1:0]bank;
wire[10:0]sa;wire cke,oe;wire[3:0]dqm;
sdf_sdram_service service(clk,resetn,take,er,re,ra,rdata,we,wa,wd,
 valid,br,w,addr,data,mask,bv,rsp_ready,bd,initialized,sf,cmd,bank,sa,cke,dqm,oe,dq,32'h12345678);
integer cycle=0,start=-1,read_due=-1,write_due=-1,next_sample=0,samples=0;
integer done[0:4],target[0:4],i,bytes=0,t_done=-1,fft_done=-1,all_done=-1;
reg[4:0]waiting=0;
always @(negedge clk)if(resetn)begin
 take=start>=0 && samples<8192 && cycle>=next_sample && er;
 re=cycle+1==read_due;ra=held;
 we=cycle+1==write_due;wa=held;wd=cycle;
 commit=start<0 && er;
 for(i=0;i<5;i=i+1)if(i!=1 && start>=0 && !v[i] && !waiting[i] && done[i]<target[i])begin
  v[i]=1;w[i]=(i==0 || done[i]%2==0);a[i*21+:21]=21'h10000+i*21'h4000+(done[i]%128)*8;
 end
end
always @(posedge clk)begin
 cycle=cycle+1;
 if(resetn)begin
  if(commit && commit_ready)begin start=cycle;next_sample=cycle+1+FFT_PHASE;end
  if(take && er)begin read_due=cycle+1;write_due=cycle+6;held=samples%4096;samples=samples+1;next_sample=cycle+13;end
  if(sv)begin bytes=bytes+1;if(bytes==29952)t_done=cycle-start;end
  for(i=0;i<5;i=i+1)if(i!=1)begin
   if(v[i] && br[i])begin v[i]<=0;waiting[i]<=1;end
   if(bv[i] && rsp_ready[i])begin waiting[i]<=0;done[i]=done[i]+1;end
  end
  if(samples==8192 && cycle>write_due && service.cache.state==2 && service.cache.word_index==0 && !service.cache.pending && fft_done<0)fft_done=cycle-start;
  if(t_done>=0 && fft_done>=0 && done[0]==target[0] && done[2]==target[2] && done[3]==target[3] && done[4]==target[4] && all_done<0)all_done=cycle-start;
 end
 #1;if(sf || rf)$fatal(1,"fault");
 if(all_done>=0)begin
  $display("RESULT T_bytes=%0d T_done=%0d FFT_samples=%0d FFT_done=%0d all_done=%0d deadline=160380 deadline_missed=%0d",bytes,t_done,samples,fft_done,all_done,all_done>160380);
  $finish;
 end
 if(cycle>500000)$fatal(1,"not drained T=%0d FFT=%0d FFT_done=%0d",bytes,samples,fft_done);
end
initial begin
 for(i=0;i<5;i=i+1)begin target[i]=0;done[i]=0;end
 target[0]=936;target[2]=2091;target[3]=744;target[4]=325;
 repeat(3)@(negedge clk);resetn=1;
end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ReaderServiceTest(unittest.TestCase):
 def test_finite_contention_diagnostic(self):
  files=['t_soft_reader.sv','sdf_sdram_service.sv','sdf_delay_cache.sv','sdram_client_arbiter.sv','dual_sdram_burst.sv']
  traces=[]
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(TB)
   for phase in range(13):
    with self.subTest(phase=phase):
     subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.FFT_PHASE={phase}','-o',str(p/'sim'),str(p/'tb.sv'),*(str(ROOT/'rtl'/f)for f in files)],check=True)
     r=subprocess.run(['vvp',str(p/'sim')],text=True,capture_output=True,timeout=90)
     self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('RESULT',r.stdout)
     values={k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',r.stdout)}
     traces.append(dict(phase=phase,**values));print('phase',phase,r.stdout.splitlines()[0],flush=True)
  result=dict(scope=__doc__,traces=traces,all_finite_deadlines_pass=all(not t['deadline_missed']for t in traces),source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()for f in [Path(__file__),*(ROOT/'rtl'/x for x in files)]},whole_receiver_verified=False,formal_routes=0)
  if os.environ.get('T_SOFT_SERVICE_REPORT'):Path(os.environ['T_SOFT_SERVICE_REPORT']).write_text(json.dumps(result,indent=2)+'\n')

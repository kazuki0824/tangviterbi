"""Actual six-client arbiter, current FFT/cache/controller; synthetic backgrounds."""
import hashlib,json,os,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_sdf_cache_contention import contention_bench,ARBITER
from test_shared_sdf_fft import ROOT,ARCHIVE,ORACLE,vectors

CLIENTS=r'''
module memory_system(input wire clk,resetn,valid,output wire ready,
 input wire wr,input wire[20:0]addr,input wire[255:0]data,
 output wire rv,output wire[255:0]response);
parameter FFT_FIRST=1;
localparam PERIOD=160380;
reg[5:0]cv,cw;wire[5:0]cr,crv;reg[125:0]ca;reg[1535:0]cd;
wire qv,qr,qw,sv,sr;wire[20:0]qa;wire[255:0]qd,sd;wire[31:0]qm;
reg[255:0]expect_data;reg[31:0]reference_mem[0:16383];
integer rates[0:4],arrived[0:4],finished[0:4],acc[0:4],peak[0:4],miss[0:4];
integer elapsed=0,first_overflow=-1,fft_requests=0,c,k,x,idx;
assign ready=cr[5];assign rv=crv[5];assign response=sd;
sdram_client_arbiter arb(clk,resetn,cv,cr,cw,ca,cd,192'd0,crv,6'b111111,
 ,qv,qr,qw,qa,qd,qm,sv,sr,sd);
raw_memory memory(clk,resetn,qv,qr,qw,qa,qd,sv,sd,sr,qm);
initial begin
 if(!FFT_FIRST)$fatal(1,"RTL has fixed FFT priority");
 rates[0]=936;rates[1]=936;rates[2]=2091;rates[3]=744;rates[4]=325;
 for(c=0;c<5;c=c+1)begin arrived[c]=0;finished[c]=0;acc[c]=0;peak[c]=0;miss[c]=0;end
 for(c=0;c<16384;c=c+1)reference_mem[c]=32'hbadc0ffe;
end
always @* begin
 cv=0;cw=0;ca=0;cd=0;idx=0;
 cv[5]=valid;cw[5]=wr;ca[105+:21]=addr;cd[1280+:256]=data;
 for(x=0;x<5;x=x+1)begin
  idx=finished[x];cv[x]=arrived[x]>finished[x] && (x!=1 || finished[1]<finished[0]);
  if(x<2)begin cw[x]=x==0;ca[x*21+:21]=4096+(idx%128)*8;end
  else begin cw[x]=(idx%2)==0;ca[x*21+:21]=4096+(x-1)*2048+((idx/2)%128)*8;end
  cd[x*256+:256]={8{32'h12345678}};
 end
end
always @(negedge clk)if(resetn && memory.initialized)begin
 elapsed=elapsed+1;
 for(c=0;c<5;c=c+1)begin
  acc[c]=acc[c]+rates[c];
  if(acc[c]>=PERIOD)begin acc[c]=acc[c]-PERIOD;arrived[c]=arrived[c]+1;end
  if(arrived[c]-finished[c]>peak[c])peak[c]=arrived[c]-finished[c];
  if(first_overflow<0 && arrived[c]-finished[c]>256)first_overflow=elapsed;
 end
end
always @(posedge clk)if(resetn)begin
 for(c=0;c<5;c=c+1)begin
  if(cv[c] && cr[c])begin
   if(c==0 && finished[0]-finished[1]>=128)$fatal(1,"T unread ring overwrite");
   expect_data=0;
   for(k=0;k<8;k=k+1)begin
    expect_data[k*32+:32]=reference_mem[ca[c*21+:21]+k];
    if(cw[c])reference_mem[ca[c*21+:21]+k]=cd[c*256+k*32+:32];
   end
  end
  if(crv[c])begin
   if(!cw[c] && sd!==expect_data)$fatal(1,"background mismatch");
   if(elapsed-((longint'(finished[c])+1)*PERIOD+rates[c]-1)/rates[c]>PERIOD)miss[c]=miss[c]+1;
   finished[c]=finished[c]+1;
  end
 end
 if(crv[5])fft_requests=fft_requests+1;
end
task report;
 begin
 $display("LOAD elapsed=%0d fft_requests=%0d first_overflow=%0d",elapsed,fft_requests,first_overflow);
 for(c=0;c<5;c=c+1)$display("BG id=%0d arrived=%0d finished=%0d peak=%0d pending=%0d misses=%0d",c,arrived[c],finished[c],peak[c],arrived[c]-finished[c],miss[c]);
 end
endtask
endmodule
'''

def rtl_bench():
 s=contention_bench().replace(ARBITER,CLIENTS)
 # Add real controller response backpressure and request masks to the pin model.
 start=s.index('module raw_memory(');end=s.index('endmodule',start)
 raw=s[start:end].replace('output wire rv,output wire[255:0]response);','output wire rv,output wire[255:0]response,input wire rsp_ready,input wire[31:0]masks);')
 raw=raw.replace("data,32'd0,rv,1'b1,response",'data,masks,rv,rsp_ready,response')
 return s[:start]+raw+s[end:]

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class RTLArbiterIntegrationTest(unittest.TestCase):
 def test_current_fft_through_rtl_arbiter(self):
  n=8192;words=vectors(n,'random');results=[]
  expected=sum((ORACLE.reference_fft(words[f*n:(f+1)*n],ORACLE.load_quarter()) for f in range(3)),[])
  for paced in (0,1):
   with tempfile.TemporaryDirectory() as d:
    p=Path(d);(p/'tb.sv').write_text(rtl_bench());(p/'input.hex').write_text(''.join(f'{w:08x}\n' for w in words))
    subprocess.run(['iverilog','-g2012','-s','tb','-Ptb.FFT_FIRST=1',f'-Ptb.PACED={paced}','-o',str(p/'sim'),str(p/'tb.sv'),
     *(str(ROOT/'rtl'/f) for f in ('sdram_client_arbiter.sv','shared_sdf_fft.sv','sdf_delay_cache.sv','dual_sdram_burst.sv')),
     str(ARCHIVE/'rtl/research_sdf_twiddle.sv')],cwd=ARCHIVE,check=True,timeout=30)
    run=subprocess.run(['vvp',str(p/'sim'),f'+INPUT_HEX={p/"input.hex"}'],cwd=ARCHIVE,capture_output=True,text=True,timeout=120)
    self.assertEqual(run.returncode,0,run.stdout[-3000:]+run.stderr)
   rows=[s.split() for s in run.stdout.splitlines() if s.startswith('OUT ')]
   self.assertEqual(len(rows),3*n)
   for k,row in enumerate(rows):
    self.assertEqual(int(row[1]),k);self.assertEqual(int(row[2]),ORACLE.bit_reverse(k%n,13));self.assertEqual(int(row[3],16),expected[k])
   summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS '))
   frames=list(map(int,re.search(r'frame_cycles=(\d+,\d+,\d+)',summary)[1].split(',')))
   bg=[{k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',s)} for s in run.stdout.splitlines() if s.startswith('BG ')]
   for r in bg:self.assertEqual(r['arrived'],r['finished']+r['pending'])
   results.append(dict(paced=bool(paced),summary=summary,frame_intervals=[b-a for a,b in zip(frames,frames[1:])],background=bg,
    load=next(s for s in run.stdout.splitlines() if s.startswith('LOAD ')),input_queue=next(s for s in run.stdout.splitlines() if s.startswith('INPUT_QUEUE ')),oracle_bit_exact=True))
  report=dict(scope=__doc__,results=results,target_symbol_clocks=160380,actual_arbiter_RTL=True,actual_background_RTL=False,PHY_verified=False,
   source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
    (Path(__file__),ROOT/'rtl/sdram_client_arbiter.sv',ROOT/'rtl/shared_sdf_fft.sv',ROOT/'rtl/sdf_delay_cache.sv',ROOT/'rtl/dual_sdram_burst.sv',
     ROOT/'tests/test_sdf_cache_contention.py',ROOT/'tests/test_sdf_delay_cache.py',ROOT/'tests/test_common_clock_sdram.py',ROOT/'tests/test_shared_sdf_fft.py')})
  print(json.dumps(report))
  if os.environ.get('SDF_RTL_ARBITER_REPORT'):Path(os.environ['SDF_RTL_ARBITER_REPORT']).write_text(json.dumps(report,indent=2)+'\n')

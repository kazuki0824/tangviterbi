"""Real SDF/cache/controller with uniformly released synthetic background clients.
Not actual K7/deinterleaver/S-frame RTL, finite FIFO implementation, or PHY.
"""
import hashlib,json,os,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_sdf_delay_cache import bench
from test_shared_sdf_fft import ROOT,ARCHIVE,ORACLE,vectors

ARBITER=r'''
module memory_system(input wire clk,resetn,valid,output wire ready,
 input wire wr,input wire[20:0]addr,input wire[255:0]data,
 output wire rv,output wire[255:0]response);
parameter FFT_FIRST=1;
localparam PERIOD=160380;
reg busy=0,issued=0;integer owner=0,rr=0,chosen,c,k,off,idx;
reg qv=0,qw=0;wire qr,sv;reg[20:0]qa=0;reg[255:0]qd=0;wire[255:0]sd;
reg[255:0]expect_data;reg[31:0]reference_mem[0:16383];
integer rates[0:4],arrived[0:4],finished[0:4],acc[0:4],peak[0:4],miss[0:4];
integer elapsed=0,first_overflow=-1,started=0,fft_requests=0;
assign ready=busy && owner==5 && !issued && qr;
assign rv=busy && owner==5 && issued && sv;
assign response=sd;
raw_memory memory(clk,resetn,qv,qr,qw,qa,qd,sv,sd);
initial begin
 rates[0]=936;rates[1]=936;rates[2]=2091;rates[3]=744;rates[4]=325;
 for(c=0;c<5;c=c+1)begin arrived[c]=0;finished[c]=0;acc[c]=0;peak[c]=0;miss[c]=0;end
 for(c=0;c<16384;c=c+1)reference_mem[c]=32'hbadc0ffe;
end
always @(negedge clk)if(resetn)begin
 if(memory.initialized)begin
  started=1;elapsed=elapsed+1;
  for(c=0;c<5;c=c+1)begin
   acc[c]=acc[c]+rates[c];
   if(acc[c]>=PERIOD)begin acc[c]=acc[c]-PERIOD;arrived[c]=arrived[c]+1;end
   if(arrived[c]-finished[c]>peak[c])peak[c]=arrived[c]-finished[c];
   if(first_overflow<0 && arrived[c]-finished[c]>256)first_overflow=elapsed;
  end
 end
 if(!busy)begin
  chosen=-1;
  if(FFT_FIRST && valid)chosen=5;
  for(off=0;off<6;off=off+1)begin
   c=(rr+off)%6;
   if(chosen<0)begin
    if(c==5)begin if(valid)chosen=5;end
    else if(arrived[c]>finished[c] && (c!=1 || finished[1]<finished[0]))chosen=c;
   end
  end
  if(chosen>=0)begin
   owner=chosen;rr=(chosen+1)%6;busy=1;issued=0;qv=1;
   if(chosen==5)begin qw=wr;qa=addr;qd=data;end
   else begin
    idx=finished[chosen];
    if(chosen<2)begin
     if(chosen==0 && idx-finished[1]>=128)$fatal(1,"T unread ring overwrite");
     qw=chosen==0;qa=4096+(idx%128)*8;end
    else begin qw=(idx%2)==0;qa=4096+(chosen-1)*2048+((idx/2)%128)*8;end
    qd={8{32'h12345678}};expect_data=0;
    for(k=0;k<8;k=k+1)expect_data[k*32+:32]=reference_mem[qa+k];
   end
  end
 end
end
always @(posedge clk)if(resetn && busy)begin
 if(!issued && qv && qr)begin
  issued<=1;qv<=0;
  if(owner<5 && qw)for(k=0;k<8;k=k+1)reference_mem[qa+k]=qd[k*32+:32];
 end else if(issued && sv)begin
  if(owner==5)fft_requests=fft_requests+1;
  else begin
   if(!qw && sd!==expect_data)$fatal(1,"background data mismatch");
   if(elapsed-((longint'(finished[owner])+1)*PERIOD+rates[owner]-1)/rates[owner]>PERIOD)miss[owner]=miss[owner]+1;
   finished[owner]=finished[owner]+1;
  end
  busy<=0;issued<=0;
 end
end
task report;
 begin
 $display("LOAD elapsed=%0d fft_requests=%0d first_overflow=%0d",elapsed,fft_requests,first_overflow);
 for(c=0;c<5;c=c+1)$display("BG id=%0d arrived=%0d finished=%0d peak=%0d pending=%0d misses=%0d",c,arrived[c],finished[c],peak[c],arrived[c]-finished[c],miss[c]);
 end
endtask
endmodule
'''

def contention_bench():
 s=bench().replace('module memory_system(', 'module raw_memory(').replace('localparam MEM_WORDS=4096;', 'localparam MEM_WORDS=16384;')
 s=s.replace('module tb;', 'module tb;parameter FFT_FIRST=1,PACED=0;integer epoch=-1,offered=0,phase_count=0,peak_input=0;')
 s=s.replace('memory_system memory(', 'memory_system #(.FFT_FIRST(FFT_FIRST)) memory(')
 s=s.replace(' in_valid=sent<FRAMES*N;', '''
 if(epoch<0 && external_ready)epoch=cycles;
 offered=0;
 if(epoch>=0)begin
  phase_count=(((cycles-epoch)%160380)*64)/1215;
  if(phase_count>N)phase_count=N;
  offered=((cycles-epoch)/160380)*N+phase_count;
  if(offered>FRAMES*N)offered=FRAMES*N;
 end
 if(PACED && offered-sent>peak_input)peak_input=offered-sent;
 in_valid=sent<FRAMES*N && (!PACED || sent<offered);''')
 s=s.replace(' $finish;',' memory.report();\n $display("INPUT_QUEUE paced=%0d peak_samples=%0d epoch=%0d",PACED,peak_input,epoch);\n $finish;',1)
 return s+ARBITER

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ContentionTest(unittest.TestCase):
 def test_real_cache_with_uniform_background(self):
  n=8192;words=vectors(n,'random');results=[]
  expected=sum((ORACLE.reference_fft(words[f*n:(f+1)*n],ORACLE.load_quarter()) for f in range(3)),[])
  for priority,paced in ((0,0),(1,0),(1,1)):
   with tempfile.TemporaryDirectory() as d:
    p=Path(d);(p/'tb.sv').write_text(contention_bench());(p/'input.hex').write_text(''.join(f'{w:08x}\n' for w in words))
    subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.FFT_FIRST={priority}',f'-Ptb.PACED={paced}','-o',str(p/'sim'),str(p/'tb.sv'),
      *(str(ROOT/'rtl'/f) for f in ('shared_sdf_fft.sv','sdf_delay_cache.sv','dual_sdram_burst.sv')),
      str(ARCHIVE/'rtl/research_sdf_twiddle.sv')],cwd=ARCHIVE,check=True,timeout=30)
    run=subprocess.run(['vvp',str(p/'sim'),f'+INPUT_HEX={p/"input.hex"}'],cwd=ARCHIVE,capture_output=True,text=True,timeout=90)
    self.assertEqual(run.returncode,0,run.stdout[-3000:]+run.stderr)
   rows=[s.split() for s in run.stdout.splitlines() if s.startswith('OUT ')]
   self.assertEqual(len(rows),3*n)
   for k,row in enumerate(rows):
    self.assertEqual(int(row[2]),ORACLE.bit_reverse(k%n,13));self.assertEqual(int(row[3],16),expected[k],f'bin {k}')
   summary=next(s for s in run.stdout.splitlines() if s.startswith('PASS '))
   frames=list(map(int,re.search(r'frame_cycles=(\d+,\d+,\d+)',summary)[1].split(',')))
   bg=[{k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',s)} for s in run.stdout.splitlines() if s.startswith('BG ')]
   load=next(s for s in run.stdout.splitlines() if s.startswith('LOAD '))
   self.assertEqual(len(bg),5)
   for r in bg:self.assertEqual(r['arrived'],r['finished']+r['pending']);self.assertGreater(r['finished'],0)
   input_queue=next(s for s in run.stdout.splitlines() if s.startswith("INPUT_QUEUE "))
   results.append(dict(fft_first=bool(priority),paced=bool(paced),input_queue=input_queue,summary=summary,frame_intervals=[b-a for a,b in zip(frames,frames[1:])],background=bg,load=load,oracle_bit_exact=True))
  report=dict(scope=__doc__,results=results,target_symbol_clocks=160380,actual_background_RTL=False,PHY_verified=False,
    source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in (Path(__file__),ROOT/'tests/test_sdf_delay_cache.py',ROOT/'tests/test_shared_sdf_fft.py',ROOT/'tests/test_common_clock_sdram.py',ROOT/'rtl/sdf_delay_cache.sv',ROOT/'rtl/shared_sdf_fft.sv',ROOT/'rtl/dual_sdram_burst.sv')})
  print(json.dumps(report))
  if os.environ.get('SDF_CONTENTION_REPORT'):Path(os.environ['SDF_CONTENTION_REPORT']).write_text(json.dumps(report,indent=2)+'\n')

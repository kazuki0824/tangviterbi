"""Finite-queue admission probe with paced clients on real controller RTL.
Arrival/address models are explicit favorable test inputs, not full demod RTL.
"""
import hashlib,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_common_clock_sdram import BENCH,ROOT
from test_sdram_service_probe import fft_requests

EXTRA=r'''
parameter BATCH=1,SYMBOLS=4;
localparam PERIOD=160380,HORIZON=SYMBOLS*PERIOD,QCAP=256;
integer rates[0:5],arrived[0:5],finished[0:5],acc[0:5],peak[0:5],miss[0:5];
integer source[0:REQUESTS-1],issued_at[0:REQUESTS-1];
reg bg_types[0:6143];reg[20:0] bg_addresses[0:6143];
reg[31:0] reference_mem[0:MEM_WORDS-1];
integer start=-1,elapsed=0,last_t=-1000,cache=0,peak_cache=0,consume_acc=0;
integer underruns=0,first_overflow=-1,overflow_source=-1,read_before_write=0,overwrite=0;
integer steady_ref_gap=0,eligible_since=-1,max_eligible_wait=0;
integer rr=1,batch_left=0,owner=1,q=0,b,c,chosen,off,idx,tgap=0,maxgap=0;
'''
DRIVER=r'''
always @(negedge clk)if(start>=0)begin
 elapsed=cycle-start;
 if(finished[0]<finished[1] && cache<=160)begin
  if(eligible_since<0)eligible_since=cycle;
 end else eligible_since=-1;
 if(elapsed>0 && elapsed%PERIOD==0)$display("SNAP symbol=%0d FFT_pending=%0d",elapsed/PERIOD,arrived[2]-finished[2]);
 if(elapsed<HORIZON)begin
  for(c=1;c<6;c=c+1)begin
   acc[c]=acc[c]+rates[c];
   if(acc[c]>=PERIOD)begin acc[c]=acc[c]-PERIOD;arrived[c]=arrived[c]+1;end
   if(arrived[c]-finished[c]>peak[c])peak[c]=arrived[c]-finished[c];
   if(first_overflow<0 && arrived[c]-finished[c]>QCAP)begin first_overflow=elapsed;overflow_source=c;end
  end
  if(elapsed>=PERIOD)begin
   consume_acc=consume_acc+29952;
   if(consume_acc>=PERIOD)begin
    consume_acc=consume_acc-PERIOD;
    if(cache>0)cache=cache-1;else underruns=underruns+1;
   end
  end
 end
 if(elapsed>=HORIZON)begin
  $display("RESULT batch=%0d symbols=%0d max_eligible_wait=%0d underruns=%0d first_overflow=%0d overflow_source=%0d peak_cache=%0d max_T_gap=%0d overwrite=%0d read_before_write=%0d refresh_gap=%0d steady_refresh_gap=%0d",BATCH,SYMBOLS,max_eligible_wait,underruns,first_overflow,overflow_source,peak_cache,maxgap,overwrite,read_before_write,max_ref_gap,steady_ref_gap);
  for(c=1;c<6;c=c+1)$display("CLIENT id=%0d arrived=%0d finished=%0d peak=%0d pending=%0d deadline_misses=%0d",c,arrived[c],finished[c],peak[c],arrived[c]-finished[c],miss[c]);
  $finish;
 end
end
initial begin
 for(i=0;i<MEM_WORDS;i=i+1)begin mem[i]=0;reference_mem[i]=0;end
 for(i=0;i<4;i=i+1)begin rows[i]=0;activated[i]=-10000;precharged[i]=-10000;lastwrite[i]=-10000;end
 for(i=0;i<6;i=i+1)begin rates[i]=0;arrived[i]=0;finished[i]=0;acc[i]=0;peak[i]=0;miss[i]=0;end
 rates[1]=936;rates[2]=6144;rates[3]=2091;rates[4]=744;rates[5]=325;
 $readmemh("bg_types.hex",bg_types);$readmemh("bg_addresses.hex",bg_addresses);
 repeat(3)@(negedge clk);resetn=1;wait(initialized);
 @(posedge clk);#1;start=cycle;
 forever begin
  // Select after arrival/cache updates at the falling edge.
  @(negedge clk);#1;chosen=-1;
  if(finished[0]<finished[1] && cache<=160 && (cycle-last_t>=104))chosen=0;
  if(chosen<0)begin
   if(batch_left>0 && arrived[owner]>finished[owner])chosen=owner;
   else begin
    for(off=0;off<5;off=off+1)begin
     c=1+(rr-1+off)%5;
     if(chosen<0 && arrived[c]>finished[c])chosen=c;
    end
    if(chosen>0)begin owner=chosen;batch_left=BATCH;rr=1+chosen%5;end
   end
  end
  if(chosen<0 && finished[0]<finished[1] && cache<=160)chosen=0;
  if(chosen>=0)begin
   idx=finished[chosen];source[q]=chosen;wr=0;addr=0;
   case(chosen)
    0:begin addr=(idx%1872)*8;if(idx>=finished[1])read_before_write=read_before_write+1;end
    1:begin wr=1;addr=(idx%1872)*8;if(idx-finished[0]>=1872)overwrite=overwrite+1;end
    2:begin wr=bg_types[idx%6144];addr=65536+bg_addresses[idx%6144];end
    3:begin wr=idx%2;addr=131072+((idx/2)%1024)*8;end
    4:begin wr=idx%2;addr=163840+((idx/2)%1024)*8;end
    5:begin wr=idx%2;addr=196608+((idx/2)%1024)*8;end
   endcase
   // All background addresses are disjoint; FFT uses its concrete mapping.
   addresses[q]=addr;data={8{32'h12345678}};masks=0;expected[q]=0;
   for(b=0;b<8;b=b+1)begin
    if(wr)reference_mem[addr+b]=32'h12345678;
    else expected[q][32*b+:32]=reference_mem[addr+b];
   end
   if(chosen>0)issued_at[q]=start+((longint'(idx)+1)*PERIOD+rates[chosen]-1)/rates[chosen];else issued_at[q]=cycle;
   valid=1;
   @(posedge clk);while(!ready)@(posedge clk);
   @(negedge clk);valid=0;
   wait(received==q+1);q=q+1;
  end
 end
end
endmodule
'''


def bench():
    s=BENCH.replace('dual_sdram_burst #(',EXTRA+'\ndual_sdram_burst #(',1)
    s=s.replace('wire rsp_ready=!(cycle>=31858 && cycle<34858);','wire rsp_ready=1;')
    s=s.replace('received=received+1;',r'''
   if(source[received]==0)begin
    cache=cache+32;if(cache>192)$fatal(1,"cache overflow");
    if(cache>peak_cache)peak_cache=cache;
    if(finished[0]>0 && cycle-last_t>maxgap)maxgap=cycle-last_t;
    if(eligible_since>=0 && cycle-eligible_since>max_eligible_wait)max_eligible_wait=cycle-eligible_since;
    eligible_since=-1;last_t=cycle;
   end else begin
    if(cycle-issued_at[received]>PERIOD)miss[source[received]]=miss[source[received]]+1;
    batch_left=batch_left-1;
   end
   finished[source[received]]=finished[source[received]]+1;
   received=received+1;''')
    s=s.replace('cycle>300000','cycle>4000000')
    s=s.replace('lastref=cycle;refs=refs+1;', 'if(refs>=9 && cycle-lastref>steady_ref_gap)steady_ref_gap=cycle-lastref;\n    lastref=cycle;refs=refs+1;')
    marker='initial begin\n for(i=0;i<MEM_WORDS;i=i+1)mem[i]=0;'
    assert marker in s
    s=s[:s.index(marker)]+DRIVER
    # Only one descriptor is outstanding. Recycle scoreboard slots so a long
    # run does not allocate one wide Verilog vector for every past request.
    s=s.replace('received>=REQUESTS || ', '').replace('if(received==REQUESTS)', "if(1'b0)")
    for name in ('addresses','expected','source','issued_at'):
        for index in ('q','received'):
            s=s.replace(f'{name}[{index}]', f'{name}[{index}%REQUESTS]')
    return s


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class FiniteClientsTest(unittest.TestCase):
    def test_paced_clients_and_finite_admission(self):
        results=[]
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/'tb.sv').write_text(bench())
            for k,name in enumerate(('bg_types','bg_addresses')):
                (p/f'{name}.hex').write_text('\n'.join(f'{row[k]:x}' for row in fft_requests())+'\n')
            for batch,symbols in ((1,4),(8,4),(32,4),(64,4),(128,4),(128,16)):
                subprocess.run(['iverilog','-g2012','-s','tb','-Ptb.REQUESTS=1024','-Ptb.MEM_WORDS=262144',
                    f'-Ptb.BATCH={batch}',f'-Ptb.SYMBOLS={symbols}','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_sdram_burst.sv')],check=True,timeout=30)
                r=subprocess.run(['vvp',str(p/'sim')],cwd=p,text=True,capture_output=True,timeout=90)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                def parse(line):return {k:int(v) for k,v in (x.split('=') for x in line.split()[1:])}
                result=parse(next(x for x in r.stdout.splitlines() if x.startswith('RESULT')))
                result['snapshots']=[parse(x) for x in r.stdout.splitlines() if x.startswith('SNAP')]
                result['clients']=[parse(x) for x in r.stdout.splitlines() if x.startswith('CLIENT')]
                self.assertEqual(result['read_before_write'],0)
                self.assertLessEqual(result['peak_cache'],192)
                self.assertLessEqual(result['steady_refresh_gap'],1203)
                result['candidate_pass']=result['underruns']==0 and result['first_overflow']<0 and result['overwrite']==0 and all(x['deadline_misses']==0 for x in result['clients'])
                results.append(result)
                if os.environ.get("SDRAM_FINITE_REPORT"):
                    Path(os.environ["SDRAM_FINITE_REPORT"]+".partial").write_text(json.dumps(results,indent=2)+"\n")
        if os.environ.get('SDRAM_FINITE_REPORT'):
            Path(os.environ['SDRAM_FINITE_REPORT']).write_text(json.dumps(dict(scope=__doc__,results=results,
                source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
                (Path(__file__),ROOT/'tests/test_common_clock_sdram.py',ROOT/'tests/test_sdram_service_probe.py',ROOT/'rtl/dual_sdram_burst.sv')},
                all_client_real_arrivals_verified=False,phy_qualified=False),indent=2)+'\n')

if __name__=='__main__':unittest.main()

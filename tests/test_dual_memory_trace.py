"""Real dense-ring BL8 addresses and byte masks through the connected FFT bus.

Finite trace; grouped T producer and sequential S CW storage are explicit
contracts, not a claim that RF clients or their permutation are implemented.
"""
import hashlib,json,os,random,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_dual_fft_memory import BENCH,ROOT,packed
from dual_fft_reference import frame
from dual_memory_trace import make_trace

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class DenseTrace(unittest.TestCase):
    def test_masked_layout_with_fft(self):
        frames=int(os.environ.get('DUAL_TRACE_FRAMES','4')); results=[]
        for logn in map(int,os.environ.get('DUAL_TRACE_MODES','11,12,13').split(',')):
            isolate=int(os.environ.get('DUAL_TRACE_ISOLATE','1'))
            phase_div=int(os.environ.get('DUAL_TRACE_PHASE_DIV','0'))
            phase_ns=259875*(1<<(logn-11))//phase_div if phase_div else 0
            layers=json.loads(os.environ['DUAL_TRACE_LAYERS']) if os.environ.get('DUAL_TRACE_LAYERS') else None
            trace,contract=make_trace(logn-10,frames,phase_ns=phase_ns,isolate=bool(isolate),layers=layers)
            priority=int(os.environ.get('DUAL_TRACE_PRIORITY','1'))
            if priority:
                self.assertEqual(isolate,1)
                s_trace=[x for x in trace if x['source']==1]
                trace=[x for x in trace if x['source']!=1]
            contract['S_priority']=bool(priority)
            with tempfile.TemporaryDirectory() as temp:
                p=Path(temp);n=1<<logn
                rng=random.Random(logn)
                samples=[(rng.randrange(-12000,12001),rng.randrange(-12000,12001)) for _ in range(n*frames)]
                expected=[x for k in range(frames) for x in frame(samples[k*n:(k+1)*n])]
                for name,values in (('input',samples),('expected',expected)):
                    (p/f'{name}.hex').write_text('\n'.join(f'{packed(x):08x}' for x in values)+'\n')
                for key in ('at','deadline','write','address','data','mask','expected','source'):
                    (p/f'trace_{key}.hex').write_text('\n'.join(f'{x[key]:x}' for x in trace)+'\n')
                if priority:
                    for key in ('at','deadline','write','address','data','mask','expected'):
                        (p/f's_{key}.hex').write_text('\n'.join(f'{x[key]:x}' for x in s_trace)+'\n')
                bench=BENCH.replace('65536','2097152')
                bench=bench.replace('.INIT_CYCLES(32)',f'.INIT_CYCLES(32),.FFT_BANK_ISOLATION({isolate}),.BACKGROUND_FIFO_DEPTH(256)')
                if isolate:
                    bench=bench.replace('reg ov=0;',"function integer fp(input integer idx);fp=(idx/256)*1024+idx%256;endfunction\nreg ov=0;")
                    bench=bench.replace('mem[i]=input_words','mem[fp(i)]=input_words').replace('mem[16384+i]','mem[fp(16384+i)]').replace('mem[16384+N]','mem[fp(16384+N)]').replace('mem[8192+N]','mem[fp(8192+N)]')
                bench=bench.replace("dout,din,32'd0,);","dout,din,omask,fifo_level);")
                defs=f'''localparam REQUESTS={len(trace)};
reg[63:0] at[0:REQUESTS-1],deadline[0:REQUESTS-1];
reg types[0:REQUESTS-1];reg[20:0] addresses[0:REQUESTS-1];
reg[255:0] data[0:REQUESTS-1],exp[0:REQUESTS-1];
reg[31:0] masks[0:REQUESTS-1];reg[1:0] sources[0:REQUESTS-1];
wire[15:0] fifo_level;integer peak_fifo=0,peak_external=0;
reg[31:0] omask=0;integer deadline_misses[0:3],max_pending=0;
real worst_lateness=0;
initial begin
'''
                for key,target in [('at','at'),('deadline','deadline'),('write','types'),('address','addresses'),('data','data'),('mask','masks'),('expected','exp'),('source','sources')]:
                    defs+=f'$readmemh("{p}/trace_{key}.hex",{target});\n'
                defs+='for(integer s=0;s<4;s=s+1)deadline_misses[s]=0;\nend\n'
                bench=bench.replace('reg ov=0;',defs+'reg ov=0;')
                a=bench.index('// Capture/output');b=bench.index('always @(posedge mclk)if(resetn)',a)
                bench=bench[:a]+'''always @(negedge mclk)begin
 if(active)while(produced<REQUESTS && $realtime-epoch>=at[produced])produced=produced+1;
 if(fifo_level>peak_fifo)peak_fifo=fifo_level;
 if(produced-sent>peak_external)peak_external=produced-sent;
 ov=sent<produced;
 if(sent<REQUESTS)begin ow=types[sent];oa=addresses[sent];od=data[sent];omask=masks[sent];end
 orr=1;
end
'''+bench[b:]
                a=bench.index('  if(received%2==0)');b=bench.index('  received=received+1;',a)
                bench=bench[:a]+'''  if(ord!==exp[received])$fatal(1,"masked response mismatch %0d got %h expected %h",received,ord,exp[received]);
  if($realtime-epoch>deadline[received])begin
   deadline_misses[sources[received]]=deadline_misses[sources[received]]+1;
   if($realtime-epoch-deadline[received]>worst_lateness)worst_lateness=$realtime-epoch-deadline[received];
  end
'''+bench[b:]
                # Continue arrivals after last FFT completes until the finite
                # trace is fully released. Never silently discard trailing work.
                bench=bench.replace('if(run==FRAMES-1)active=0;','')
                bench=bench.replace('wait(received==produced);','wait(received==REQUESTS);active=0;')
                bench=bench.replace(' $finish;',''' $display("QUEUE fifo_entries=%0d external_pending=%0d peak_bytes=%0d T_misses=%0d S_misses=%0d IO_misses=%0d management_misses=%0d lateness_ns=%0.3f",peak_fifo,peak_external,peak*32,deadline_misses[0],deadline_misses[1],deadline_misses[2],deadline_misses[3],worst_lateness);
 $finish;''')
                bench=bench.replace('"INPUT"',json.dumps(str(p/'input.hex'))).replace('"EXPECTED"',json.dumps(str(p/'expected.hex')))
                if priority:
                    bench=bench.replace('dual_fft_memory #(.INIT_CYCLES(32),.FFT_BANK_ISOLATION(1),.BACKGROUND_FIFO_DEPTH(256))',
                                        'dual_fft_memory_clients #(.INIT_CYCLES(32))')
                    bench=bench.replace('omask,fifo_level);','omask,fifo_level,sv,sready,sw,sa,sd,sm,srv,1\'b1,srd);')
                    bench=bench.replace('dut.fft.','dut.memory.fft.').replace('dut.bv','dut.memory.bv').replace('dut.br','dut.memory.br').replace('dut.bw','dut.memory.bw')
                    sdefs=f"""localparam SREQ={len(s_trace)};
reg[63:0] sat[0:SREQ-1],sdeadline[0:SREQ-1];reg stypes[0:SREQ-1];
reg[20:0] saddrs[0:SREQ-1];reg[31:0] smasks[0:SREQ-1];
reg[255:0] sdata[0:SREQ-1],sexp[0:SREQ-1];
integer ssent=0,sreceived=0,sproduced=0,speak=0,smisses=0;
wire sready,srv;wire[255:0] srd;
reg sv=0,sw=0;reg[20:0] sa=0;reg[255:0] sd=0;reg[31:0] sm=0;
initial begin
"""
                    for key,target in [('at','sat'),('deadline','sdeadline'),('write','stypes'),('address','saddrs'),('data','sdata'),('mask','smasks'),('expected','sexp')]:
                        sdefs+=f'$readmemh("{p}/s_{key}.hex",{target});\n'
                    sdefs+="""end
always @(negedge mclk)begin
 if(active)while(sproduced<SREQ && $realtime-epoch>=sat[sproduced])sproduced=sproduced+1;
 sv=ssent<sproduced;
 if(ssent<SREQ)begin sw=stypes[ssent];sa=saddrs[ssent];sd=sdata[ssent];sm=smasks[ssent];end
 if(sproduced-sreceived>speak)speak=sproduced-sreceived;
end
always @(posedge mclk)if(resetn)begin
 if(sv&&sready)ssent=ssent+1;
 if(srv)begin
  if(sreceived>=ssent || srd!==sexp[sreceived])$fatal(1,"S response mismatch %0d",sreceived);
  if($realtime-epoch>sdeadline[sreceived])smisses=smisses+1;
  sreceived=sreceived+1;
 end
end
"""
                    bench=bench.replace('reg ov=0;',sdefs+'reg ov=0;')
                    bench=bench.replace('wait(received==REQUESTS);','wait(received==REQUESTS && sreceived==SREQ);')
                    bench=bench.replace(' $display("QUEUE',' deadline_misses[1]=smisses;\n $display("SPR pending_bursts=%0d",speak);\n $display("QUEUE')
                (p/'tb.sv').write_text(bench)
                files=list((ROOT/'rtl').glob('dual_fft_*.sv'))+list((ROOT/'rtl').glob('dual_burst_*.sv'))+[ROOT/'rtl/dual_sdram_burst.sv']
                subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.LOGN={logn}',f'-Ptb.FRAMES={frames}','-Ptb.PROFILE=1','-o',str(p/'sim'),str(p/'tb.sv'),*map(str,files)],check=True,timeout=30)
                run=subprocess.run(['vvp',str(p/'sim')],cwd=ROOT,capture_output=True,text=True,timeout=frames*30+60)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                rows=[dict(kv.split('=') for kv in line.split()[1:]) for line in run.stdout.splitlines() if line.startswith('RESULT')]
                queue=[dict(kv.split('=') for kv in line.split()[1:]) for line in run.stdout.splitlines() if line.startswith('QUEUE')]
                self.assertEqual(len(rows),frames);self.assertEqual(len(queue),1)
                result=dict(contract=contract,frames=rows,queue=queue[0],FFT_deadline_pass=all(float(x['ns'])<=259875*(1<<(logn-11)) for x in rows),
                            client_deadline_pass=all(int(v)==0 for k,v in queue[0].items() if k.endswith('_misses')),
                            staging_64KiB_pass=int(queue[0]['peak_bytes'])<=65536)
                if priority:
                    result['S_peak_pending_bursts']=int(next(line.split('=')[1] for line in run.stdout.splitlines() if line.startswith('SPR')))
                results.append(result);print(json.dumps(result),flush=True)
        if os.environ.get('DUAL_TRACE_REPORT'):
            files += [Path(__file__),ROOT/'tests/test_dual_fft_memory.py',ROOT/'tests/test_dual_sdram.py',ROOT/'experiments/dual_memory_trace.py',ROOT/'experiments/dual_memory_contract.py',ROOT/'experiments/dual_fft_reference.py',ROOT/'rtl/dual_fft_quarter_q16.hex']
            Path(os.environ['DUAL_TRACE_REPORT']).write_text(json.dumps(dict(results=results,source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},scope=__doc__),indent=2)+'\n')

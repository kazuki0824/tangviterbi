"""Full-frame RTL, unrelated clocks, SDRAM pin model and competing bursts.

Host supplies vectors, never tile/pass commands. Deadline rejection is recorded
separately from functional correctness. Not physical CDC/PHY/STA qualification.
"""
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from dual_fft_reference import frame
from test_dual_sdram import BENCH as SDRAM_BENCH
# Reuse the independently implemented pin-level memory protocol checker, not
# controller internals. Strip only its old stimulus-specific address check.
MODEL=SDRAM_BENCH[SDRAM_BENCH.index('reg[31:0] mem'):SDRAM_BENCH.index('reg[255:0] held')]
MODEL=MODEL.replace('MEM_WORDS','65536')
MODEL+=SDRAM_BENCH[SDRAM_BENCH.index('always @(negedge clk)'):SDRAM_BENCH.index('  if(received==REQUESTS)')]
start=MODEL.index('  if(valid && ready)')
end=MODEL.index('  if(wleft>0)')
MODEL=MODEL[:start]+MODEL[end:]
MODEL=MODEL.replace('if(base!=addresses[received] || base+7>=MEM_WORDS)', 'if(base+7>=65536)')
MODEL=MODEL.replace('if(fault)', 'if(mfault)').replace('@(negedge clk)','@(negedge mclk)').replace('@(posedge clk)','@(posedge mclk)')
MODEL+=' end\nend\n'
BENCH=r'''`timescale 1ns/1fs
module tb;
parameter LOGN=11,PROFILE=0,PHASE=0,FRAMES=2;
parameter real BG_INTERVAL=220.424409485;
localparam N=1<<LOGN,PERIOD=259875*(1<<(LOGN-11));
reg clk=0,mclk=0;
always #3.086419753 clk=~clk;
initial begin #(PHASE);forever #3.703703704 mclk=~mclk;end
reg resetn=0,start=0;reg[3:0] mode=LOGN;
reg[20:0] ib=0,mb=8192,ob=16384;
wire busy,done,ffault,overflow,initialized,mfault;
reg ov=0;wire ore;reg ow=0;reg[20:0] oa=0;reg[255:0] od=0;
wire orv;reg orr=1;wire[255:0] ord;
wire[2:0] cmd;wire[1:0] bank;wire[10:0] a;wire cke,oe;wire[3:0] dqm;wire[31:0] dout;reg[31:0] din=0;
dual_fft_memory #(.INIT_CYCLES(32)) dut(clk,mclk,resetn,start,mode,ib,mb,ob,
 busy,done,ffault,overflow,ov,ore,ow,oa,od,orv,orr,ord,
 initialized,mfault,cmd,bank,a,cke,dqm,oe,dout,din);
reg[31:0] input_words[0:FRAMES*N-1],expected[0:FRAMES*N-1];
integer run=0,corecycles=0,firstcycle,produced=0,peak=0,waitcycles=0,maxwait=0,collisions=0,overlap=0;
integer fft_reads=0,fft_writes=0;
real next_arrival=0,started_at=0,elapsed=0,epoch=0;
reg active=0;reg[255:0] held;reg holding=0;
// Capture/output + T/S memory + management: 145.17448441724304 MB/s offered.
always @(negedge mclk)begin
 if(active && PROFILE!=0)begin
  while($realtime>=next_arrival)begin
   produced=produced+(PROFILE==3?32:1);
   next_arrival=next_arrival+BG_INTERVAL*(PROFILE==3?32:1);
  end
 end
 ov=sent<produced;ow=(sent%2)==0;
 oa=32768+(PROFILE==2 ? (32'(sent/2)%4)*256+((sent/8)%2)*1024 : (32'(sent/2)%2048)*8);
 od={8{32'hcafe0000|32'(sent/2)}};
 orr=!(PROFILE==3 && (cycle%2000)>=700 && (cycle%2000)<1000);
end
always @(posedge mclk)if(resetn)begin
 if(ov && ore)begin sent=sent+1;if(waitcycles>maxwait)maxwait=waitcycles;waitcycles=0;end
 else if(ov)waitcycles=waitcycles+1;
 if(holding && (!orv || ord!==held))$fatal(1,"other response changed during stall");
 holding=orv&&!orr;held=ord;
 if(orv && orr)begin
  if(received>=sent)$fatal(1,"unowned response");
  if(received%2==0)begin if(ord!==256'd0)$fatal(1,"write ack corrupt");end
  else if(ord!=={8{32'hcafe0000|32'(received/2)}})$fatal(1,"other data corrupt %0d",received);
  received=received+1;
 end
 if(produced-received>peak)peak=produced-received;
 if(dut.bv&&ov)collisions=collisions+1;
 if(dut.bv&&dut.br)begin
  if(dut.bw)fft_writes=fft_writes+1;else fft_reads=fft_reads+1;
 end
end
always @(posedge clk)if(resetn)begin
 corecycles=corecycles+1;
 if(dut.fft.tile_busy && dut.fft.state!=0)overlap=overlap+1;
 if(dut.fft.tile_busy && dut.fft.state!=0 && dut.fft.dma_bank==dut.fft.compute_bank)$fatal(1,"bank ownership collision");
 if(dut.fft.owner[0]==0 && dut.fft.owner[1]==0 && busy && dut.fft.tile_busy)$fatal(1,"compute bank freed");
 if(ffault && active && !start)$fatal(1,"FFT fault");
 if(corecycles>FRAMES*250000)$fatal(1,"timeout");
end
initial begin
 for(i=0;i<65536;i=i+1)mem[i]=32'hdeadc0de;
 for(i=0;i<4;i=i+1)begin rows[i]=0;activated[i]=-10000;precharged[i]=-10000;lastwrite[i]=-10000;end
 $readmemh("INPUT",input_words);$readmemh("EXPECTED",expected);
 for(i=0;i<N;i=i+1)mem[i]=input_words[i];
 repeat(5)@(negedge clk);resetn=1;
 wait(initialized);repeat(10)@(negedge clk);
 mb=0;start=1;@(negedge clk);start=0;
 if(!ffault||busy)$fatal(1,"bad frame contract accepted");mb=8192;
 for(run=0;run<FRAMES;run=run+1)begin
  @(negedge clk);
  if(run>0)while($realtime<epoch+run*PERIOD)@(negedge clk);
  if(run==0)begin epoch=$realtime;next_arrival=$realtime+PHASE;active=1;end
  for(i=0;i<N;i=i+1)mem[i]=input_words[run*N+i];
  start=1;firstcycle=corecycles;started_at=epoch+run*PERIOD;
  @(negedge clk);start=0;
  wait(done);@(negedge clk);elapsed=$realtime-started_at;if(run==FRAMES-1)active=0;
  if(overflow)$fatal(1,"unexpected arithmetic clipping");
  for(i=0;i<N;i=i+1)if(mem[16384+i]!==expected[run*N+i])$fatal(1,"FFT mismatch bin %0d got %h expected %h",i,mem[16384+i],expected[run*N+i]);
  if(mem[16384+N]!==32'hdeadc0de || (N<8192 && mem[8192+N]!==32'hdeadc0de))$fatal(1,"out of frame write");
  if(fft_reads!=(run+1)*N/4 || fft_writes!=(run+1)*N/4)$fatal(1,"wrong burst count");
  if(max_ref_gap>1053 || overlap==0)$fatal(1,"no refresh/overlap coverage");
  if(PROFILE!=0 && collisions==0)$fatal(1,"contention not exercised");
  $display("RESULT run=%0d cycles=%0d ns=%0.3f peak_queue=%0d max_grant_wait=%0d max_refresh_gap=%0d overlap=%0d reads=%0d writes=%0d other_completed=%0d",run,corecycles-firstcycle,elapsed,peak,maxwait,max_ref_gap,overlap,fft_reads,fft_writes,received);
  if(run==FRAMES-1)begin wait(received==produced);repeat(10)@(negedge clk);end
 end
 $finish;
end
''' + MODEL + '\nendmodule\n'

def packed(x):return (x[0]&65535)|((x[1]&65535)<<16)

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class MemoryIntegration(unittest.TestCase):
    def test_frames_banks_contention_cdc_and_deadlines(self):
        results=[]
        frames=int(os.environ.get('DUAL_FFT_MEMORY_FRAMES','2'))
        background=float(os.environ.get('DUAL_FFT_MEMORY_BACKGROUND','145.17448441724304'))
        modes=[int(x) for x in os.environ.get('DUAL_FFT_MEMORY_MODES','11,12,13').split(',')]
        profiles=[int(x) for x in os.environ.get('DUAL_FFT_MEMORY_PROFILES','0,1,2,3').split(',')]
        self.assertGreaterEqual(frames,2)
        self.assertGreater(background,0)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for logn in modes:
                rng=random.Random(0x162135+logn)
                samples=[(rng.randrange(-12000,12001),rng.randrange(-12000,12001)) for _ in range(frames<<logn)]
                expected=[v for k in range(frames) for v in frame(samples[k*(1<<logn):(k+1)*(1<<logn)])]
                for name,values in (('input',samples),('expected',expected)):
                    (p/f'{name}.hex').write_text('\n'.join(f'{packed(x):08x}' for x in values)+'\n')
                bench=BENCH.replace('"INPUT"',json.dumps(str(p/'input.hex'))).replace('"EXPECTED"',json.dumps(str(p/'expected.hex')))
                (p/'tb.sv').write_text(bench)
                for profile,phase in ((0,0),(1,0),(2,2),(3,5)):
                    if profile not in profiles:continue
                    files=list((ROOT/'rtl').glob('dual_fft_*.sv'))+list((ROOT/'rtl').glob('dual_burst_*.sv'))+[ROOT/'rtl/dual_sdram_burst.sv']
                    subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.LOGN={logn}',f'-Ptb.PROFILE={profile}',f'-Ptb.PHASE={phase}',f'-Ptb.FRAMES={frames}',f'-Ptb.BG_INTERVAL={32000/background}',
                        '-o',str(p/'sim'),str(p/'tb.sv'),*map(str,files)],check=True,timeout=30)
                    r=subprocess.run(['vvp',str(p/'sim')],cwd=ROOT,capture_output=True,text=True,timeout=max(120,frames*15))
                    self.assertEqual(r.returncode,0,f'N={1<<logn}, profile={profile}:\n'+r.stdout+r.stderr)
                    rows=[dict(kv.split('=') for kv in line.split()[1:]) for line in r.stdout.splitlines() if line.startswith('RESULT')]
                    self.assertEqual(len(rows),frames)
                    print(f'N={1<<logn} profile={profile} ns={[row["ns"] for row in rows]}',flush=True)
                    for row in rows:
                        row={k:float(v) if k=='ns' else int(v) for k,v in row.items()}
                        period=259875*(1<<(logn-11));row.update(n=1<<logn,profile=profile,phase_ns=phase,
                            period_ns=period,deadline_pass=row['ns']<=period,deadline_margin_ns=period-row['ns'],peak_queue_bytes=32*row['peak_queue'])
                        results.append(row)
            if os.environ.get('DUAL_FFT_MEMORY_REPORT'):
                source_files=files+[Path(__file__),ROOT/'tests/test_dual_sdram.py',ROOT/'experiments/dual_fft_reference.py',ROOT/'rtl/dual_fft_quarter_q16.hex']
                Path(os.environ['DUAL_FFT_MEMORY_REPORT']).write_text(json.dumps(dict(results=results,
                    source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in source_files},
                    core_MHz=162,memory_MHz=135,background_offered_MBps=background,frames_per_condition=frames,
                    scope='Finite digital test, full frame RTL and real controller commands with two clocks. No analog CDC/PHY/STA or all-phase arrival proof. Deadline failures retained.'),indent=2)+'\n')
if __name__=='__main__':unittest.main()

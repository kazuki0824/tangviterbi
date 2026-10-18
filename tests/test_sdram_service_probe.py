"""Actual SDRAM controller + experimental testbench arbiter under saturation.

Reuses the independent pin-command/data/timing monitor. This is not an RTL
arbiter, a real arrival/deadline trace, a PHY test, or all-client integration.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_common_clock_sdram import BENCH, ROOT

EXTRA=r'''
parameter GUARD=112,CONFLICT=0;
reg source[0:REQUESTS-1];
reg bg_types[0:6143];reg[20:0] bg_addresses[0:6143];
reg[31:0] reference_mem[0:MEM_WORDS-1];
integer last_t=-1,max_t_gap=0,t_count=0,b_count=0;
integer start_cycle=-1,end_cycle=0,t_index=0,b_index=0,q,b;
integer t_gap_violations=0;
'''
DRIVER=r'''
initial begin
 for(i=0;i<MEM_WORDS;i=i+1)begin mem[i]=0;reference_mem[i]=0;end
 for(i=0;i<4;i=i+1)begin rows[i]=0;activated[i]=-10000;precharged[i]=-10000;lastwrite[i]=-10000;end
 repeat(3)@(negedge clk);resetn=1;
 if(CONFLICT==2)begin $readmemh("bg_types.hex",bg_types);$readmemh("bg_addresses.hex",bg_addresses);end
 wait(initialized);
 // Configuration/init fully finishes before the first request is accepted.
 for(q=0;q<REQUESTS;q=q+1)begin
  @(negedge clk);
  source[q]=(last_t<0 || cycle-last_t>=GUARD);
  if(source[q])begin
   wr=0;addr=(t_index%128)*8;t_index=t_index+1;
  end else begin
   wr=b_index%2;
   if(CONFLICT==2)begin wr=bg_types[b_index%6144];addr=8192+bg_addresses[b_index%6144];end
   else if(CONFLICT==1)addr=8192+(b_index%2)*1024;else addr=8192+(b_index%1024)*8;
   b_index=b_index+1;
  end
  addresses[q]=addr;data={8{32'h12345678}};masks=0;
  expected[q]=0;
  for(b=0;b<8;b=b+1)begin
   if(wr)reference_mem[addr+b]=32'h12345678;
   else expected[q][32*b+:32]=reference_mem[addr+b];
  end
  valid=1;
  @(posedge clk);while(!ready)@(posedge clk);
  @(negedge clk);valid=0;
  // One descriptor outstanding. This deliberately pays a dispatch bubble.
  wait(received==q+1);
 end
end
endmodule
'''


def bench():
    s=BENCH.replace('dual_sdram_burst #(',EXTRA+'\ndual_sdram_burst #(',1)
    s=s.replace('wire rsp_ready=!(cycle>=31858 && cycle<34858);','wire rsp_ready=1;')
    s=s.replace('if(sent==RSTART)rbegin=cycle;','if(start_cycle<0)start_cycle=cycle;\n   if(sent==RSTART)rbegin=cycle;')
    s=s.replace('received=received+1;',r'''
   if(source[received])begin
    if(last_t>=0)begin
     if(cycle-last_t>max_t_gap)max_t_gap=cycle-last_t;
     if(cycle-last_t>160)t_gap_violations=t_gap_violations+1;
    end
    last_t=cycle;t_count=t_count+1;
   end else b_count=b_count+1;
   end_cycle=cycle;
   received=received+1;''')
    old='$display("PASS requests=%0d refreshes=%0d max_refresh_gap=%0d read_cycles=%0d write_cycles=%0d",received,refs,max_ref_gap,rend-rbegin,wend-wbegin);'
    new='$display("PASS requests=%0d refreshes=%0d max_refresh_gap=%0d T_count=%0d BG_count=%0d elapsed=%0d max_T_gap=%0d violations=%0d",received,refs,max_ref_gap,t_count,b_count,end_cycle-start_cycle,max_t_gap,t_gap_violations);'
    assert old in s
    s=s.replace(old,new).replace('cycle>300000','cycle>1000000')
    marker='initial begin\n for(i=0;i<MEM_WORDS;i=i+1)mem[i]=0;'
    assert marker in s
    return s[:s.index(marker)]+DRIVER


def fft_requests():
    """Six Q15 Mode-3 transfers using the existing FFT row/column mapping."""
    requests=[(1,a) for a in range(0,8192,8)]
    for tile in range(8):
        requests.extend((0,row*64+tile*8) for row in range(128))
        requests.extend((1,8192+row*64+tile*8) for row in range(128))
    for tile in range(8):
        for lane in range(16):
            requests.extend((0,8192+(tile*16+lane)*64+point) for point in range(0,64,8))
        for point in range(64):
            requests.extend((1,16384+point*128+tile*16+lane) for lane in range(0,16,8))
    requests.extend((0,a) for a in range(16384,24576,8))
    assert len(requests)==6144
    return requests


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ServiceProbeTest(unittest.TestCase):
    def test_actual_controller_competition(self):
        results=[]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'tb.sv').write_text(bench())
            background=fft_requests()
            for k,name in enumerate(("bg_types","bg_addresses")):
                (p/f"{name}.hex").write_text("\n".join(f"{row[k]:x}" for row in background)+"\n")
            for conflict in (0,1,2):
                for guard in (160,112,104):
                    subprocess.run(['iverilog','-g2012','-s','tb','-Ptb.REQUESTS=12000',
                        f'-Ptb.GUARD={guard}',f'-Ptb.CONFLICT={conflict}',
                        '-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_sdram_burst.sv')],check=True,timeout=30)
                    run=subprocess.run(['vvp',str(p/'sim')],cwd=p,text=True,capture_output=True,timeout=60)
                    self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                    line=next(x for x in run.stdout.splitlines() if x.startswith('PASS'))
                    r={k:int(v) for k,v in (item.split('=') for item in line.split()[1:])}
                    r.update(guard=guard,background=('sequential','alternating_same_bank_rows','FFT_six_transfers')[conflict],
                        T_MBps=r['T_count']*32*(1080/7)/r['elapsed'],
                        BG_MBps=r['BG_count']*32*(1080/7)/r['elapsed'])
                    self.assertEqual(r['T_count']+r['BG_count'],12000)
                    self.assertGreater(r['T_count'],0);self.assertGreater(r['BG_count'],0)
                    if guard==160:self.assertGreater(r['violations'],0)
                    if guard==104:self.assertEqual(r['violations'],0)
                    results.append(r)
        if os.environ.get('SDRAM_SERVICE_REPORT'):
            Path(os.environ['SDRAM_SERVICE_REPORT']).write_text(json.dumps(dict(
                scope=__doc__,results=results,phy_qualified=False,all_client_deadlines_verified=False,
                source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
                    (Path(__file__),ROOT/'tests/test_common_clock_sdram.py',ROOT/'rtl/dual_sdram_burst.sv')}
            ),indent=2)+'\n')

if __name__=='__main__':unittest.main()

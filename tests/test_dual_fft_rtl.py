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
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from dual_fft_reference import fft,frame,cross,twiddle

def packed(x):return (int(x[0])&65535)|((int(x[1])&65535)<<16)
def unpack(v):
    a=v&65535;b=v>>16
    return (a if a<32768 else a-65536,b if b<32768 else b-65536)

TILE_TB=r'''`timescale 1ns/1ps
module tb;
parameter JOBS=1,N=128,LANE_BITS=0,CONCURRENT=0;
localparam LANES=1<<LANE_BITS,WORDS=N*LANES;
reg clk=0;always #5 clk=~clk;
reg resetn=0,load=0,start=0,read=0,bank=0,dma_bank=0;
reg[9:0] li=0,ri=0;reg[31:0] data=0;
wire ready,busy,done,rv,overflow;wire[31:0] rd;wire[5:0] ti;
reg[35:0] rom[0:63],w;reg[31:0] input_words[0:JOBS*WORDS-1];
integer job,i,cycles;
always @(posedge clk)w<=rom[ti];
dual_fft_tile dut(clk,resetn,3'($clog2(N)),3'(LANE_BITS),dma_bank,bank,
 load,ready,li,data,start,busy,done,read,ri,rv,rd,ti,w[17:0],w[35:18],overflow);
initial begin
 $readmemh("input.hex",input_words);$readmemh("twiddle.hex",rom);
 repeat(3)@(negedge clk);resetn=1;
 for(job=0;job<JOBS;job=job+1)begin
  bank=job%2;dma_bank=bank;
  if(!CONCURRENT || job==0)for(i=0;i<WORDS;i=i+1)begin
   @(negedge clk);load=1;li=i;data=input_words[job*WORDS+i];
   if(!ready)$fatal(1,"load blocked");
  end
  @(negedge clk);load=0;start=1;
  @(negedge clk);start=0;cycles=0;
  if(CONCURRENT && job+1<JOBS)begin dma_bank=!bank;load=1;li=0;data=input_words[(job+1)*WORDS];end
  while(!done && cycles<20000)begin
   @(posedge clk);if(load && !ready)$fatal(1,"other bank blocked");#1;cycles=cycles+1;
   @(negedge clk);
   if(CONCURRENT && job+1<JOBS && cycles<WORDS)begin
    load=1;li=cycles;data=input_words[(job+1)*WORDS+cycles];
   end else load=0;
  end
  dma_bank=bank;load=0;
  if(!done || cycles!=WORDS*$clog2(N))$fatal(1,"wrong duration %d",cycles);
  $display("META %0d %0d %0d",job,cycles,overflow);
  for(i=0;i<WORDS;i=i+1)begin
   @(negedge clk);read=1;ri=i;
   @(posedge clk);#1;if(!rv)$fatal(1,"missing output");
   $display("OUT %0d %0d %08h",job,i,rd);
  end
  @(negedge clk);read=0;
 end
 $finish;
end
endmodule
'''
CROSS_TB=r'''`timescale 1ns/1ps
module tb;
parameter WORDS=1;
reg clk=0;always #5 clk=~clk;
reg resetn=0,iv=0,ready=0;wire ir,ov,overflow;wire[31:0] od;
reg[31:0] input_words[0:WORDS-1];reg[35:0] coefs[0:WORDS-1];
reg[31:0] x=0;reg[35:0] w=0;integer i,cycles;
dual_fft_cross dut(clk,resetn,iv,ir,x[15:0],x[31:16],w[17:0],w[35:18],ov,ready,od,overflow);
initial begin
 $readmemh("input.hex",input_words);$readmemh("coef.hex",coefs);
 repeat(3)@(negedge clk);resetn=1;
 for(i=0;i<WORDS;i=i+1)begin
  @(negedge clk);iv=1;x=input_words[i];w=coefs[i];ready=0;
  @(posedge clk);if(!ir)$fatal(1,"not ready");
  @(negedge clk);iv=0;cycles=0;
  while(!ov && cycles<5)begin @(posedge clk);#1;cycles=cycles+1;end
  if(!ov || cycles!=2)$fatal(1,"cross latency");
  $display("OUT %0d %08h %0d",i,od,overflow);
  repeat(i%3)begin @(posedge clk);#1;if(!ov)$fatal(1,"lost stalled output");end
  @(negedge clk);ready=1;
  @(negedge clk);ready=0;
 end
 $finish;
end
endmodule
'''

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class TileRTL(unittest.TestCase):
    measurements=[]
    @classmethod
    def tearDownClass(cls):
        if os.environ.get('DUAL_FFT_REPORT'):
            Path(os.environ['DUAL_FFT_REPORT']).write_text(json.dumps(dict(
                scope='RTL core/cross simulations with host-orchestrated frame passes; no RTL SDRAM controller or full receiver',
                source_sha256={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('rtl/dual_fft_tile.sv','rtl/dual_fft_cross.sv','rtl/dual_fft_twiddle.sv','rtl/dual_fft_quarter_q16.hex')},
                measurements=cls.measurements),indent=2)+'\n')
    def run_tiles(self,jobs,lanes=1,concurrent=False):
        n=len(jobs[0]);self.assertEqual(len(jobs)%lanes,0)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'tb.sv').write_text(TILE_TB)
            words=[packed(jobs[j+lane][i]) for j in range(0,len(jobs),lanes) for i in range(n) for lane in range(lanes)]
            (p/'input.hex').write_text('\n'.join(f'{w:08x}' for w in words)+'\n')
            (p/'twiddle.hex').write_text('\n'.join(f'{(wi&262143)<<18|(wr&262143):09x}' for wr,wi in [twiddle(j,128) for j in range(64)])+'\n')
            subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.JOBS={len(jobs)//lanes}',f'-Ptb.N={n}',f'-Ptb.LANE_BITS={lanes.bit_length()-1}',f'-Ptb.CONCURRENT={int(concurrent)}','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_fft_tile.sv')],check=True,timeout=30)
            r=subprocess.run(['vvp',str(p/'sim')],cwd=p,capture_output=True,text=True,timeout=90)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        out=[[None]*n for _ in jobs];flags=[]
        for line in r.stdout.splitlines():
            if line.startswith('OUT '):
                _,job,index,value=line.split();job=int(job);index=int(index)
                out[job*lanes+index%lanes][index//lanes]=unpack(int(value,16))
            elif line.startswith('META '):flags.append(int(line.split()[-1]))
        self.assertEqual(len(flags),len(jobs)//lanes)
        for i in range(0,len(jobs),lanes):
            refs=[fft(x) for x in jobs[i:i+lanes]]
            self.assertEqual(out[i:i+lanes],[x[0] for x in refs])
            self.assertEqual(flags[i//lanes],any(x[1] for x in refs))
        return out
    def run_cross(self,products):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'tb.sv').write_text(CROSS_TB)
            (p/'input.hex').write_text('\n'.join(f'{packed(x):08x}' for x,w in products)+'\n')
            (p/'coef.hex').write_text('\n'.join(f'{(w[1]&262143)<<18|(w[0]&262143):09x}' for x,w in products)+'\n')
            subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.WORDS={len(products)}','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_fft_cross.sv')],check=True,timeout=30)
            r=subprocess.run(['vvp',str(p/'sim')],cwd=p,capture_output=True,text=True,timeout=90)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        out=[]
        for line in r.stdout.splitlines():
            if line.startswith('OUT '):
                _,i,value,flag=line.split();value=unpack(int(value,16));expected,overflow=cross(*products[int(i)])
                self.assertEqual((value,int(flag)),(expected,overflow));out.append(value)
        self.assertEqual(len(out),len(products));return out
    def test_global_twiddle_rom_all_phases(self):
        bench="""module tb;
reg clk=0;always #5 clk=~clk;reg[12:0] phase=0;
wire signed[17:0] r,i;integer k;
dual_fft_twiddle dut(clk,phase,r,i);
initial begin for(k=0;k<8192;k=k+1)begin
 @(negedge clk);phase=k;@(posedge clk);#1;$display("W %0d %0d %0d",k,r,i);
end $finish;end
endmodule
"""
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'tb.sv').write_text(bench)
            subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_fft_twiddle.sv')],check=True,timeout=30)
            r=subprocess.run(['vvp',str(p/'sim')],cwd=ROOT,text=True,capture_output=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        rows=[line.split() for line in r.stdout.splitlines() if line.startswith('W ')]
        self.assertEqual(len(rows),8192)
        for _,k,re,im in rows:self.assertEqual((int(re),int(im)),twiddle(int(k),8192))

    def test_tiles_and_saturation(self):
        rng=random.Random(8128)
        for n in (32,64,128):
            jobs=[[(0,0)]*n,[(16000,-16000)]*n,
                  [(16000 if i==0 else 0,0) for i in range(n)],
                  [(rng.randrange(-16000,16001),rng.randrange(-16000,16001)) for _ in range(n)],
                  [(32767 if i%3 else -32768,32767) for i in range(n)]]
            self.run_tiles(jobs)
            self.run_tiles((jobs*8)[:16],lanes=8,concurrent=True)
            if n<=64:self.run_tiles((jobs*16)[:32],lanes=16,concurrent=True)
    def test_all_modes_all_bins_against_dft(self):
        rng=np.random.default_rng(8192)
        for n in (2048,4096,8192):
            for case in ('random','tone'):
                if case=='random':x=rng.integers(-12000,12001,n)+1j*rng.integers(-12000,12001,n)
                else:x=np.rint(16000*np.cos(2*np.pi*19*np.arange(n)/n))+1j*np.rint(16000*np.sin(2*np.pi*19*np.arange(n)/n))
                samples=[(int(z.real),int(z.imag)) for z in x]
                out=frame(samples,lambda jobs:self.run_tiles(jobs,lanes=8),self.run_cross)
                z=np.array([complex(*v) for v in out]);expected=np.fft.fft(x)/n
                err=np.abs(z-expected);snr=10*np.log10(np.sum(np.abs(expected)**2)/np.sum(err**2))
                self.assertLess(float(max(err)),8)
                self.measurements.append(dict(n=n,case=case,max_complex_error_LSB=float(max(err)),SNR_dB=float(snr),bins_checked=n,bit_exact_integer_oracle=True))
if __name__=='__main__':unittest.main()

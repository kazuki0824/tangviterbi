"""Actual S byte permutation, finite packet buffers and SDRAM ownership.
Independent TX reference creates on-air bytes, not memory descriptors.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
BENCH=r'''`timescale 1ns/1ps
module tb;
parameter SUPERFRAMES=3, INPUT_PERIOD=18, RESPONSE_DELAY=20, STOP_OUTPUT=0, OUT_INTERVAL=1;
localparam INPUTS=SUPERFRAMES*8*48*203, OUTPUTS=SUPERFRAMES*8*48*204;
reg clk=0,resetn=0;always #3.703704 clk=~clk;
reg[7:0] stimulus[0:INPUTS-1],expected[0:OUTPUTS-1];
reg[7:0] mem[0:172031];
integer cycle=0,sent=0,received=0,writes=0,reads=0,stalls=0,peak=0,elapsed=0;
integer i,idx,countdown=0,first_output=-1,last_input=-1;
wire iv=sent<INPUTS && cycle%INPUT_PERIOD==0;
wire ir,ov,clast,slast,qv,qr,qw,sr,fault;
wire[7:0] od;wire[20:0] qa;wire[255:0] qd;wire[31:0] qm;
wire[1:0] pending;wire[3:0] owners;
reg sv=0,active=0;reg[255:0] sd=0;
wire ordy=(!STOP_OUTPUT||cycle>INPUTS*INPUT_PERIOD) && cycle%OUT_INTERVAL==0 && (OUT_INTERVAL!=1||cycle%47>13);
assign qr=!active && cycle%11>2;
dual_s_frame_dma dut(clk,resetn,iv,ir,stimulus[sent],ov,ordy,od,clast,slast,
 qv,qr,qw,qa,qd,qm,sv,sr,sd,pending,owners,fault);
reg held=0,oh=0;reg[309:0] saved;reg[9:0] savedout;
always @(posedge clk)if(resetn)begin
 cycle<=cycle+1;
 if(fault)$fatal(1,"fault");
 if(iv&&ir)begin sent<=sent+1;if(sent==INPUTS-1)last_input=cycle;end
 if(iv&&!ir)stalls=stalls+1;
 if(pending>peak)peak=pending;
 if(held&&(!qv||{qw,qa,qd,qm}!==saved))$fatal(1,"request not held");
 held<=qv&&!qr;saved<={qw,qa,qd,qm};
 if(oh&&(!ov||{slast,clast,od}!==savedout))$fatal(1,"output not held");
 oh<=ov&&!ordy;savedout<={slast,clast,od};
 if(ov&&ordy)begin
  if(first_output<0)first_output=cycle;
  if(od!==expected[received])$fatal(1,"permutation %0d got %h expected %h",received,od,expected[received]);
  if(clast!==(received%204==203)||slast!==(received%(384*204)==384*204-1))$fatal(1,"boundary");
  received<=received+1;
  if(received+1==OUTPUTS)begin
   for(i=0;i<172032;i=i+1)if(i%224>=204&&mem[i]!==8'ha5)$fatal(1,"padding corrupt");
   $display("RESULT input_bytes=%0d output_bytes=%0d writes=%0d reads=%0d input_stalls=%0d peak_packets=%0d first_output_cycle=%0d last_input_cycle=%0d final_cycle=%0d",sent,received+1,writes,reads,stalls,peak,first_output,last_input,cycle);$finish;
  end
 end
 if(qv&&qr)begin
  if(qa[9:8]==0||qa[2:0]!=0)$fatal(1,"partition/alignment");
  idx=(((qa>>10)*3+((qa>>8)&3)-1)*256+(qa&255))*4-5690880;
  if(idx<0||idx+31>=172032)$fatal(1,"range %d",idx);
  if(qw)begin
   if(owners[(idx/86016)*2+:2]!==2'd1)$fatal(1,"write not owned");
   for(i=0;i<32;i=i+1)if(!qm[i])mem[idx+i]=qd[i*8+:8];
   writes=writes+1;sd<=0;
  end else begin
   if(owners[(idx/86016)*2+:2]!==2'd3)$fatal(1,"read before commit");
   for(i=0;i<32;i=i+1)sd[i*8+:8]<=mem[idx+i];
   reads=reads+1;
  end
  active<=1;countdown<=RESPONSE_DELAY+cycle%17;
 end
 if(active&&!sv)begin
  if(countdown==0)sv<=1;else countdown<=countdown-1;
 end
 if(sv&&sr)begin sv<=0;active<=0;end
 if(cycle>INPUTS*INPUT_PERIOD*3+1000000)$fatal(1,"timeout");
end
initial begin
 $readmemh("input.hex",stimulus);$readmemh("expected.hex",expected);
 for(i=0;i<172032;i=i+1)mem[i]=8'ha5;
 repeat(3)@(negedge clk);resetn=1;
end
endmodule
'''

def reference(superframes):
    """Transmitter matrix: each slot has 8 rows and 203 payload columns."""
    incoming=[];expected=[]
    for sf in range(superframes):
        original=[[[((sf*53+f*29+s*7+b*11)^(b>>2))&255
                    for b in range(1,204)] for s in range(48)] for f in range(8)]
        columns=[[original[f][s][b] for b in range(203) for f in range(8)] for s in range(48)]
        for f in range(8):
            for s in range(48):
                incoming.extend(columns[s][f*203:(f+1)*203])
                expected.extend([0x47]+original[f][s])
    return incoming,expected

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class SFrameDMA(unittest.TestCase):
    def test_permutation_ownership_and_stalls(self):
        results=[]
        cases=[(0,1),(1,1),(0,16)]
        if 'DUAL_S_STOP_CASES' in os.environ:
            cases=[(int(x),int(os.environ.get('DUAL_S_OUT_INTERVAL','1'))) for x in os.environ['DUAL_S_STOP_CASES'].split(',')]
        for stopped,interval in cases:
            with self.subTest(stopped=stopped,interval=interval),tempfile.TemporaryDirectory() as temp:
                p=Path(temp);incoming,expected=reference(3)
                for name,data in [('input',incoming),('expected',expected)]:
                    (p/f'{name}.hex').write_text('\n'.join(f'{v:02x}' for v in data)+'\n')
                (p/'tb.sv').write_text(BENCH)
                subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.STOP_OUTPUT={stopped}',f"-Ptb.OUT_INTERVAL={interval}",'-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_s_frame_dma.sv')],check=True,timeout=60)
                run=subprocess.run(['vvp',str(p/'sim')],cwd=p,capture_output=True,text=True,timeout=180)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                row={k:int(v) for k,v in (kv.split('=') for kv in next(line for line in run.stdout.splitlines() if line.startswith('RESULT ')).split()[1:])}
                self.assertEqual(row['reads'],3*384*7)
                self.assertEqual(row['writes'],3*5040)
                self.assertEqual(row['output_bytes'],len(expected))
                self.assertLessEqual(row['peak_packets'],2)
                if stopped:self.assertGreater(row['input_stalls'],0)
                else:self.assertEqual(row['input_stalls'],0)
                results.append(dict(output_stop=bool(stopped),output_interval_clocks=interval,**row));print(json.dumps(results[-1]),flush=True)
        if os.environ.get('DUAL_S_FRAME_REPORT'):
            files=[Path(__file__),ROOT/'rtl/dual_s_frame_dma.sv']
            Path(os.environ['DUAL_S_FRAME_REPORT']).write_text(json.dumps(dict(results=results,source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},scope='48 active TC8PSK slots. Synthetic response latency; not FFT simultaneous WCET.'),indent=2)+'\n')

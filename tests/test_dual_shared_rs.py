"""Mixed-stream corrected RS RTL against independent polynomial division."""
import hashlib
from functools import lru_cache
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'experiments'))
from check_isdb_rs import encode, vectors
from s3_rs_isdb import source

BENCH = r'''`timescale 1ns/1ps
module tb;
parameter BLOCKS=1, STALL=0;
reg clk=0; always #5 clk=~clk;
reg resetn=0;
reg[2:0] pending,credit;
reg[23:0] bytes;
wire[2:0] ready,grant;
wire valid,first,last,fail;
wire[1:0] owner; wire[7:0] data_out;
reg[7:0] received[0:3*BLOCKS*204-1],original[0:3*BLOCKS*188-1];
integer head[0:2],ip[0:2],op[0:2],reserved[0:2];
integer cycle=0,i,total=0,previous=-1,max_gap=0,min_gap=1000000;
reg[2:0] previous_credit;
dual_shared_rs dut(clk,resetn,pending,credit,bytes,ready,grant,
                  valid,first,last,fail,owner,data_out);
always @(negedge clk) begin
 pending=0; bytes=0;
 credit=STALL && cycle%17000<5000 ? 0 : 7;
 for(integer j=0;j<3;j=j+1) begin
  pending[j]=head[j]<BLOCKS;
  if(head[j]<BLOCKS && ip[j]<(j==2?64:204))
   bytes[j*8+:8]=received[(j*BLOCKS+head[j])*204+ip[j]];
 end
end
always @(posedge clk) begin
 if(!resetn) begin
  for(i=0;i<3;i=i+1)begin head[i]=0;ip[i]=0;op[i]=0;reserved[i]=0;end
  cycle=0;total=0;previous=-1;max_gap=0;min_gap=1000000;previous_credit=0;
 end else begin
  cycle=cycle+1;
  for(i=0;i<3;i=i+1)begin
   if(grant[i])begin
    if(!previous_credit[i] || reserved[i]!=0)$fatal(1,"uncredited/double grant");
    reserved[i]=i==2?48:188;
    if(previous>=0)begin
     if(cycle-previous>max_gap)max_gap=cycle-previous;
     if(cycle-previous<min_gap)min_gap=cycle-previous;
    end
    previous=cycle;
   end
   if(ready[i])ip[i]=ip[i]+1;
  end
  if(valid)begin
   if(owner>2 || reserved[owner]<=0)$fatal(1,"output without reservation");
   if(data_out !== original[(owner*BLOCKS+head[owner])*188+op[owner]])
    $fatal(1,"mismatch owner=%d word=%d byte=%d",owner,head[owner],op[owner]);
   if(fail || first!=(op[owner]==0) || last!=(op[owner]==(owner==2?47:187)))
    $fatal(1,"bad framing/fail");
   op[owner]=op[owner]+1;reserved[owner]=reserved[owner]-1;
   if(last)begin
    if(ip[owner]!=(owner==2?64:204))$fatal(1,"input size mismatch");
    head[owner]=head[owner]+1;ip[owner]=0;op[owner]=0;total=total+1;
   end
  end
  previous_credit=credit;
  if(total==3*BLOCKS)begin
   $display("PASS blocks=%0d min_grant_gap=%0d max_grant_gap=%0d",total,min_gap,max_gap);
   $finish;
  end
  if(cycle>3*BLOCKS*6000+50000)$fatal(1,"deadlock");
 end
end
initial begin
 $readmemh("received.hex",received);$readmemh("original.hex",original);
 repeat(4)@(negedge clk);resetn=1;
 // Abort a partially consumed word and, without credit stalls, a decoding word.
 repeat(100)@(negedge clk);resetn=0;
 repeat(3)@(negedge clk);resetn=1;
 repeat(1500)@(negedge clk);resetn=0;
 repeat(3)@(negedge clk);resetn=1;
end
endmodule
'''


@lru_cache(maxsize=1)
def corpus():
    main = [(cw, data) for _, cw, data in vectors()]
    rng = random.Random(0x6448)
    data = [rng.randrange(256) for _ in range(48)]
    cw = encode(data)
    short = [(cw, data), (encode([0]*48), [0]*48)]
    for pos in range(64):
        damaged = cw.copy(); damaged[pos] ^= 0xa7
        short.append((damaged, data))
    for n in range(2, 9):
        for trial in range(8):
            damaged = cw.copy()
            for pos in rng.sample(range(64), n):
                damaged[pos] ^= rng.randrange(1, 256)
            short.append((damaged, data))
    short = (short*3)[:len(main)]
    return main, list(reversed(main)), short


class SharedRS(unittest.TestCase):
    def test_shortening_identity(self):
        for data in {tuple(data) for _, data in corpus()[2]}:
            data=list(data)
            # Check clean systematic code equality; damaged words are RTL tests.
            self.assertEqual(encode([0]*140+data), [0]*140+encode(data))

    @unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'), 'Icarus required')
    def test_mixed_rtl(self):
        streams = corpus(); blocks = len(streams[0]); rows=[]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); (p/'decoder.sv').write_text(source(True, True)); (p/'tb.sv').write_text(BENCH)
            for name, part, size in [('received',0,204),('original',1,188)]:
                values=[b for stream in streams for row in stream
                        for b in row[part]+[0]*(size-len(row[part]))]
                (p/f'{name}.hex').write_text('\n'.join(f'{v:02x}' for v in values)+'\n')
            for compact,stall in ((True,0),(True,1),(False,0),(False,1)):
                (p/'decoder.sv').write_text(source(True, compact))
                subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.BLOCKS={blocks}',f'-Ptb.STALL={stall}',
                    '-o',str(p/'sim'),str(p/'tb.sv'),str(p/'decoder.sv'),str(ROOT/'rtl/dual_shared_rs.sv')],check=True,timeout=60)
                print(f'RTL compact={compact} credit_stalls={stall}',flush=True)
                result=subprocess.run(['vvp',str(p/'sim')],cwd=p,capture_output=True,text=True,timeout=300)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn(f'PASS blocks={3*blocks}',result.stdout)
                if not stall:
                    self.assertIn('min_grant_gap=2672 max_grant_gap=2672',result.stdout)
                rows.append(dict(compact_BRAM_tables=compact,decoder_sha256=hashlib.sha256(source(True,compact).encode()).hexdigest(),credit_stalls=bool(stall),log=result.stdout.strip(),passed=True))
        report=dict(decoder_sha256=hashlib.sha256(source(True, True).encode()).hexdigest(),
                    wrapper_sha256=hashlib.sha256((ROOT/'rtl/dual_shared_rs.sv').read_bytes()).hexdigest(),
                    cases_per_stream=blocks,scenarios=rows,slot_cycles=2672,
                    scope='Functional simulation, continuous source bytes, full-word output reservations; no STA or SDRAM DMA')
        if os.environ.get('DUAL_RS_REPORT'):
            Path(os.environ['DUAL_RS_REPORT']).write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__': unittest.main()

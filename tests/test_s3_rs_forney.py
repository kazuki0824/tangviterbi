"""Check FPGA Forney against known injected channel errors, not CPU Forney."""
import ctypes as c
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from check_isdb_rs import vectors,gf,encode
import test_s3_rs_offload as host

class ForneyTest(unittest.TestCase):
 def test_262_codewords_invalid_commands_reset_and_output_ownership(self):
  host.OffloadTest.setUpClass();lib=host.OffloadTest.lib
  table=host.Tables();solution=host.Solution();lib.s3_rs_tables_init(c.byref(table))
  commands=[];expected=[]
  for name,rx,payload in vectors():
   syndrome=[];root=1
   for _ in range(16):
    value=0
    for byte in rx:value=gf(value,root)^byte
    syndrome.append(value);root=gf(root,2)
   self.assertEqual(lib.s3_rs_solve(c.byref(table),(c.c_uint8*16)(*syndrome),c.byref(solution)),1,name)
   corrections=[(i,a^b) for i,(a,b) in enumerate(zip(rx,encode(payload))) if a!=b]
   count=len(corrections)
   command=sum(solution.lambda_[i]<<(8*i) for i in range(9))
   command|=sum(solution.omega[i]<<(72+8*i) for i in range(16))
   command|=sum(p<<(208+8*i) for i,(p,_) in enumerate(corrections))
   command|=solution.degree<<200|count<<204
   commands.append(command);expected.append(sum(m<<(8*i) for i,(_,m) in enumerate(corrections)))
  # Reject out-of-range, duplicate/unsorted, missing-root, degree/count and
  # zero-denominator commands. Partial magnitudes must never be used on fail.
  invalid=[(1|(9<<200)|(9<<204)),(1|(1<<200)),(2),
           (commands[2]&~(255<<208))|(204<<208),
           (commands[2]&~(255<<208))|(1<<208)]
  # Build a two-error repeated position from a valid multi-error polynomial.
  two=commands[206];p=(two>>208)&255
  invalid.extend([(two&~(255<<216))|(p<<216),
                  (two&~(65535<<208))|(((two>>216)&255)<<208)|(p<<216),
                  (1|(1<<16)|(1<<200)|(1<<204)|(203<<208))])
  commands+=invalid;expected += [0]*len(invalid);n=len(commands)
  out=ROOT/'build/s3-rs-forney';out.mkdir(parents=True,exist_ok=True)
  (out/'commands.hex').write_text(''.join(f'{v:068x}\n' for v in commands))
  (out/'expected.hex').write_text(''.join(f'{v:016x}\n' for v in expected))
  tb=f'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,cv=0,ready=0;reg[271:0]cmd=0;
wire cr,valid,failed;wire[63:0]magnitudes;
s3_rs_forney dut(clk,rst,cv,cr,cmd[71:0],cmd[199:72],cmd[203:200],cmd[207:204],cmd[271:208],valid,ready,failed,magnitudes);
reg[271:0]commands[0:{n-1}];reg[63:0]expected[0:{n-1}];
reg[63:0]held;integer b,cycles,maxcycles=0;
initial begin
 $readmemh("commands.hex",commands);$readmemh("expected.hex",expected);
 repeat(3)@(negedge clk);rst=1;
 for(b=0;b<{n};b=b+1)begin
  if(b%16==0)begin
   @(negedge clk);rst=0;repeat(2)@(negedge clk);rst=1;
   cmd=commands[250];cv=1;@(negedge clk);cv=0;repeat(7+b%47)@(negedge clk);
   rst=0;repeat(2)@(negedge clk);rst=1;
   if(valid)$fatal(1,"old epoch survived reset");
  end
  if(!cr)$fatal(1,"command ownership");cmd=commands[b];cv=1;ready=0;
  @(negedge clk);cv=0;cycles=0;
  while(!valid)begin @(negedge clk);cycles=cycles+1;if(cycles>587)$fatal(1,"cycle bound");end
  if(failed!==(b>=262))$fatal(1,"status case %0d",b);
  if(!failed && magnitudes!==expected[b])$fatal(1,"magnitude case %0d",b);
  if(cycles>maxcycles)maxcycles=cycles;held=magnitudes;
  repeat(5)begin @(negedge clk);if(!valid||cr||magnitudes!==held)$fatal(1,"output ownership");end
  ready=1;@(negedge clk);ready=0;
 end
 $display("PASS Forney blocks={n} known_channel_magnitudes max_service_cycles=%0d",maxcycles);$finish;
end
endmodule'''
  (out/'tb.sv').write_text(tb)
  p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(ROOT/'rtl/s3_rs_forney.sv'),str(out/'tb.sv')],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
  p=subprocess.run(['vvp','sim'],cwd=out,capture_output=True,text=True,timeout=90)
  (out/'simulation.log').write_text(p.stdout+p.stderr)
  self.assertEqual(p.returncode,0,p.stdout+p.stderr)
  match=re.search(r'max_service_cycles=(\d+)',p.stdout);self.assertIsNotNone(match)
  (out/'result.json').write_text(json.dumps(dict(independent_codewords=262,invalid_commands=len(invalid),
   maximum_observed_cycles=int(match[1]),conservative_bound_cycles=587,
   bound_derivation='203 root steps + 8*(1 seek + 9 locator + 16 omega + 1 square + 4 derivative + 1 denominator + 15 inverse + 1 magnitude)',
   output_stalls_excluded_from_bound=True,receiver_adopted=False),indent=2)+'\n')

if __name__=='__main__':unittest.main()

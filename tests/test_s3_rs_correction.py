"""Independent complete-codeword and block ownership checks for correction."""
import json,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from check_isdb_rs import vectors,encode
class CorrectionTest(unittest.TestCase):
 def test_all_262_vectors_failed_block_stalls_reset_and_invalid_roots(self):
  out=ROOT/'build/s3-rs-correction';out.mkdir(parents=True,exist_ok=True)
  cases=[]
  for name,received,payload in vectors():
   original=encode(payload);errors=[(i,a^b) for i,(a,b) in enumerate(zip(received,original)) if a!=b]
   cases.append((received,original,errors,0))
  # RS failure must pass through a complete raw block with failure metadata.
  cases.append((cases[-1][0],cases[-1][0],[],1))
  for filename,rows in [('raw',[r[0] for r in cases]),('expected',[r[1] for r in cases])]:
   (out/(filename+'.hex')).write_text(''.join(f'{b:02x}\n' for row in rows for b in row))
  (out/'config.hex').write_text(''.join(f'{failed:x}{len(errors):x}'+
   bytes(m for _,m in errors).ljust(8,b'\0')[::-1].hex()+
   bytes(p for p,_ in errors).ljust(8,b'\0')[::-1].hex()+'\n' for _,_,errors,failed in cases))
  tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,cv=0,iv=0,ordy=0;wire cr,ir,ov,ol,of,ce;
reg[3:0] count=0;reg[63:0] pos=0,mag=0;reg cf=0;reg[7:0] data=0;wire[7:0] od;
s3_rs_correction dut(clk,resetn,cv,cr,count,pos,mag,cf,ce,iv,ir,data,ov,ordy,od,ol,of);
reg[7:0] raw[0:53651],expected[0:53651];reg[132:0] conf[0:262];
integer b,i,got,cycles=0,total=0,max_cycles=0,errors=0;reg[31:0] rng=32'h379;
reg held=0;reg[7:0] helddata;reg heldlast,heldfail;integer start_cycle;
always @(posedge clk)if(resetn)begin
 cycles=cycles+1;if(cycles>150000)$fatal(1,"timeout");
 if(ce)errors=errors+1;
 if(held&&(!ov||od!==helddata||ol!==heldlast||of!==heldfail))$fatal(1,"stalled output changed");
 held=ov&&!ordy;helddata=od;heldlast=ol;heldfail=of;
 if(ov&&ordy)begin
  if(od!==expected[b*204+got]||ol!==(got==203)||of!==(b==262))$fatal(1,"corrected block %d offset %d",b,got);
  got=got+1;total=total+1;
 end
end else held=0;
always @(negedge clk)begin
 rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);ordy=rng[2:0]!=0;
end
task config_bad(input[3:0] n,input[63:0] positions);
integer old;
begin
 old=errors;@(negedge clk);count=n;pos=positions;mag=0;cf=0;cv=1;
 @(negedge clk);cv=0;
 while(!cr)begin if(ir||ov)$fatal(1,"invalid config admitted bytes");@(negedge clk);end
 @(negedge clk);if(errors!=old+1)$fatal(1,"invalid config not rejected");
end endtask
initial begin
 $readmemh("raw.hex",raw);$readmemh("expected.hex",expected);$readmemh("config.hex",conf);
 #1;resetn=1;#1;resetn=0;#1;resetn=1;
 config_bad(9,0);config_bad(1,204);config_bad(2,64'h0303);config_bad(2,64'h0203);
 for(b=0;b<263;b=b+1)begin
  // Reset during a partial block: it must not publish bytes after reset.
  if(b%17==0)begin
   @(negedge clk);count=0;pos=0;mag=0;cf=0;cv=1;
   @(negedge clk);cv=0;while(!ir)@(negedge clk);
   // Load one pending output with the sink held, then abort asynchronously.
   force ordy=0;iv=1;data=37;@(negedge clk);iv=0;resetn=0;
   @(negedge clk);if(ov||!cr)$fatal(1,"dirty reset");resetn=1;release ordy;
  end
  got=0;start_cycle=cycles;
  @(negedge clk);{cf,count,mag,pos}=conf[b];cv=1;
  @(negedge clk);cv=0;while(!ir)@(negedge clk);
  for(i=0;i<204;i=i+1)begin
   iv=1;data=raw[b*204+i];
   @(posedge clk);while(!ir)@(posedge clk);
   @(negedge clk);iv=0;
   if(i%29==0)@(negedge clk);
  end
  while(got!=204)@(negedge clk);
  if(!cr)$fatal(1,"context released before/after output handshake");
  if(cycles-start_cycle>max_cycles)max_cycles=cycles-start_cycle;
 end
 if(total!=53652)$fatal(1,"byte count");
 $display("PASS correction blocks=263 bytes=%d bad_configs=%d max_cycles=%d dirty_resets=16",total,errors,max_cycles);$finish;
end
endmodule'''
  (out/'tb.sv').write_text(tb)
  r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(ROOT/'rtl/s3_rs_correction.sv'),str(out/'tb.sv')],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stderr)
  r=subprocess.run(['vvp','sim'],cwd=out,capture_output=True,text=True,timeout=45)
  (out/'simulation.log').write_text(r.stdout+r.stderr);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()

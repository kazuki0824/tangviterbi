"""Independent codeword syndromes and known error positions at FPGA split ports."""
from pathlib import Path
import ctypes as c,json,subprocess,sys,unittest
import test_s3_rs_offload as host
Tables=host.Tables;Solution=host.Solution
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from check_isdb_rs import vectors,gf,encode
class SplitRTLTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.cases=vectors();cls.syndromes=[]
  for _,received,_ in cls.cases:
   row=[];root=1
   for n in range(16):
    v=0
    for b in received:v=gf(v,root)^b
    row.append(v);root=gf(root,2)
   cls.syndromes.append(row)
 def run_sim(self,out,rtl,tb):
  (out/'tb.sv').write_text(tb)
  p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(ROOT/'rtl'/rtl),str(out/'tb.sv')],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
  p=subprocess.run(['vvp','sim'],cwd=out,capture_output=True,text=True,timeout=90)
  (out/'simulation.log').write_text(p.stdout+p.stderr)
  self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertIn('PASS',p.stdout)
 def test_folded_syndromes_262_blocks_reset_and_stalls(self):
  self.check_syndrome()
 def test_registered_syndromes_match_original_cycle_for_cycle(self):
  self.check_syndrome(True)
 def test_four_port_syndromes_262_independent_blocks(self):
  self.check_syndrome(parallel=True)
 def check_syndrome(self,registered=False,parallel=False):
  out=ROOT/('build/s3-rs-split-syndrome'+('-four-port' if parallel else '-registered' if registered else ''));out.mkdir(parents=True,exist_ok=True);n=len(self.cases)
  (out/'input.hex').write_text(''.join(f'{b:02x}\n' for _,rx,_ in self.cases for b in rx))
  (out/'expected.hex').write_text(''.join(f'{sum(b<<(8*j) for j,b in enumerate(row)):032x}\n' for row in self.syndromes))
  tb=f'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,iv=0,ordy=0;reg[7:0]data=0;wire ir,ov;wire[127:0]s;
s3_rs_syndrome dut(clk,rst,iv,ir,data,ov,ordy,s);
reg[7:0]input_bytes[0:{n*204-1}];reg[127:0]expected[0:{n-1}];integer b,i,cycles,maxcycles=0,warm;
initial begin $readmemh("input.hex",input_bytes);$readmemh("expected.hex",expected);
 repeat(3)@(negedge clk);rst=1;
 for(b=0;b<{n};b=b+1)begin
  if(b%16==0)begin
   @(negedge clk);rst=0;repeat(3)@(negedge clk);rst=1;
   iv=1;data=8'ha7;repeat(11+b%13)@(negedge clk);
   rst=0;iv=0;repeat(3)@(negedge clk);rst=1;
  end
  i=0;cycles=0;ordy=0;
  while(!ov)begin
   @(negedge clk);iv=i<204 && cycles%31!=5;if(i<204)data=input_bytes[b*204+i];
   @(posedge clk);if(iv&&ir)i=i+1;#1;cycles=cycles+1;
   if(cycles>2000)$fatal(1,"syndrome service/deadlock");
  end
  @(negedge clk);iv=0;
  if(s!==expected[b] || i!=204)$fatal(1,"syndrome block %0d",b);
  if(cycles>maxcycles)maxcycles=cycles;
  repeat(5)begin @(negedge clk);if(!ov||ir||s!==expected[b])$fatal(1,"output ownership");end
  ordy=1;@(negedge clk);ordy=0;
 end
 $display("PASS syndrome blocks={n} all_16_per_block reset_epochs=17 max_service_cycles=%0d",maxcycles);$finish;
end
endmodule'''
  rtl='s3_rs_syndrome.sv'
  if parallel:
   from s3_rs_syndrome_parallel import source
   (out/'syndrome.sv').write_text(source());rtl=str(out/'syndrome.sv')
  if registered:
   from s3_rs_syndrome_registered import source
   (out/'syndrome.sv').write_text(source()+'\n'+(ROOT/'rtl/s3_rs_syndrome.sv').read_text().replace('module s3_rs_syndrome(','module original_syndrome('))
   rtl=str(out/'syndrome.sv')
   tb=tb.replace('s3_rs_syndrome dut', '''wire ir_ref,ov_ref;wire[127:0]s_ref;
original_syndrome reference(clk,rst,iv,ir_ref,data,ov_ref,ordy,s_ref);
always @(posedge clk)if(rst)begin
 if(ir!==ir_ref||ov!==ov_ref||(ov&&s!==s_ref))$fatal(1,"registered status changed cycle contract");
end
s3_rs_syndrome dut''')
  self.run_sim(out,rtl,tb)
 def test_chien_known_positions_stalls_and_bad_locator(self):
  host.OffloadTest.setUpClass();lib=host.OffloadTest.lib;t=Tables();lib.s3_rs_tables_init(c.byref(t));s=Solution()
  out=ROOT/'build/s3-rs-split-chien';out.mkdir(parents=True,exist_ok=True)
  commands=[];expected=[]
  for (_,rx,payload),syndrome in zip(self.cases,self.syndromes):
   self.assertEqual(lib.s3_rs_solve(c.byref(t),(c.c_uint8*16)(*syndrome),c.byref(s)),1)
   commands.append(sum(s.lambda_[j]<<(8*j) for j in range(9))|(s.degree<<72))
   expected.append([i for i,(a,b) in enumerate(zip(rx,encode(payload))) if a!=b])
  # Invalid degree and a constant nonzero polynomial with a claimed root.
  commands.extend([(9<<72)|1,(1<<72)|1]);expected.extend([[],[]]);n=len(commands)
  (out/'commands.hex').write_text(''.join(f'{x:019x}\n' for x in commands))
  (out/'positions.hex').write_text(''.join(f'{sum(p<<(8*j) for j,p in enumerate(row))|(len(row)<<64):017x}\n' for row in expected))
  tb=f'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,cv=0,rr=0,dr=0;reg[75:0]command=0;
wire cr,rv,dv,fail;wire[7:0]pos;wire[3:0]count;
s3_rs_chien dut(clk,rst,cv,cr,command[71:0],command[75:72],rv,rr,pos,dv,dr,fail,count);
reg[75:0]commands[0:{n-1}];reg[67:0]expected[0:{n-1}];integer b,got,cycles,maxcycles=0;
initial begin $readmemh("commands.hex",commands);$readmemh("positions.hex",expected);
 repeat(3)@(negedge clk);rst=1;
 for(b=0;b<{n};b=b+1)begin
  if(b%16==0)begin
   @(negedge clk);rst=0;repeat(3)@(negedge clk);rst=1;
   cv=1;command=commands[25];@(negedge clk);cv=0;repeat(31+b%23)@(negedge clk);
   rst=0;repeat(3)@(negedge clk);rst=1;
  end
  @(negedge clk);if(!cr)$fatal(1,"not ready");cv=1;command=commands[b];dr=0;rr=0;
  @(negedge clk);cv=0;got=0;cycles=0;
  while(!dv)begin
   rr=cycles%17<10;
   @(posedge clk);
   if(rv&&rr)begin
    if(got>=expected[b][67:64] || pos!==expected[b][8*got+:8])$fatal(1,"position b=%0d got=%0d pos=%0d",b,got,pos);
    got=got+1;
   end
   #1;cycles=cycles+1;@(negedge clk);
   if(cycles>400)$fatal(1,"Chien service/deadlock");
  end
  if(fail!==(b>={len(self.cases)}) || got!=expected[b][67:64] || count!=got)$fatal(1,"result status b=%0d",b);
  if(cycles>maxcycles)maxcycles=cycles;
  repeat(3)begin @(negedge clk);if(!dv||cr)$fatal(1,"result ownership");end
  dr=1;@(negedge clk);dr=0;
 end
 $display("PASS Chien blocks={n} known_channel_positions reset_epochs=17 max_service_cycles=%0d",maxcycles);$finish;
end
endmodule'''
  self.run_sim(out,'s3_rs_chien.sv',tb)
if __name__=='__main__':unittest.main()

"""Exhaust the five-way round-robin grant contract before changing mapping."""
from pathlib import Path
import subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from s3_psram_queue_rotated import source
class ArbitrationTest(unittest.TestCase):
 def test_all_160_request_and_start_combinations(self):
  out=ROOT/'build/s3-psram-arbitration';out.mkdir(parents=True,exist_ok=True)
  (out/'queue.sv').write_text(source())
  (out/'tb.sv').write_text('''module tb;
reg clk=0;always #5 clk=~clk;
reg[2:0]rr;reg[4:0]req;integer r,m,k,chosen,expected,checked=0;
s3_psram_queue dut(.clk(clk),.resetn(1'b0));
initial begin
 for(r=0;r<5;r=r+1)for(m=0;m<32;m=m+1)begin
  rr=r;req=m;force dut.round_robin=rr;force dut.full=req[3:0];force dut.read_pending=req[4];#1;expected=-1;
  for(k=0;k<5;k=k+1)begin chosen=(r+k)%5;if(expected<0&&req[chosen])expected=chosen;end
  if(dut.found!==(expected>=0) || (expected>=0&&dut.pick!==expected[2:0]))$fatal(1,"grant r=%0d requests=%0h",r,m);
  checked=checked+1;
 end
 $display("PASS round_robin combinations=%0d",checked);$finish;
end
endmodule''')
  p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(out/'queue.sv'),str(out/'tb.sv')],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
  p=subprocess.run(['vvp','sim'],cwd=out,capture_output=True,text=True,timeout=10)
  (out/'simulation.log').write_text(p.stdout+p.stderr)
  self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertIn('combinations=160',p.stdout)
if __name__=='__main__':unittest.main()

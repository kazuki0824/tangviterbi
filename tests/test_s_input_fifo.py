"""Finite S retention: independent accepted-word queue, full/empty and wrap tests."""
import json,random,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class SInputFIFOTest(unittest.TestCase):
 def test_lossless_full_stall_and_wrap(self):
  tb=r'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0,iv=0,orr=0;reg[31:0]data=0;
wire ir,ov;wire[31:0]od;s_input_fifo dut(clk,rst,iv,ir,data,ov,orr,od);
integer t=0,peak=0,occupancy=0;reg accepted=0,stalled=0;reg[31:0]held=0,rng=32'h81271019;
initial begin
 repeat(3)@(negedge clk);rst=1;
 for(t=0;t<6000;t=t+1)begin
  @(negedge clk);
  rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
  orr=t>=800 && (t>=5000 || rng[2:0]!=0);
  if(accepted||!iv)begin iv=t<5000 && (t<800 || rng[4:3]!=0);data=rng;end
  @(posedge clk);accepted=iv&&ir;
  if(stalled && (!ov||od!==held))$fatal(1,"output changed under stall");
  stalled=ov&&!orr;held=od;
  if(accepted)begin $display("IN %x",data);occupancy=occupancy+1;end
  if(ov&&orr)begin $display("OUT %x",od);occupancy=occupancy-1;end
  if(occupancy<0 || occupancy>256)$fatal(1,"capacity");
  if(occupancy>peak)peak=occupancy;
 end
 if(occupancy!=0||peak!=256)$fatal(1,"drain/full not reached");
 $display("PASS peak=%0d",peak);$finish;
end
endmodule'''
  with tempfile.TemporaryDirectory() as temp:
   d=Path(temp);(d/'tb.sv').write_text(tb)
   p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(d/'sim'),str(ROOT/'experiments/s_input_fifo.sv'),str(d/'tb.sv')],text=True,capture_output=True);self.assertEqual(p.returncode,0,p.stderr)
   p=subprocess.run(['vvp',str(d/'sim')],text=True,capture_output=True);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
  got=[int(x.split()[1],16)for x in p.stdout.splitlines()if x.startswith('OUT ')]
  expected=[int(x.split()[1],16)for x in p.stdout.splitlines()if x.startswith('IN ')]
  self.assertEqual(got,expected);self.assertGreater(len(got),3000)
  print(f'PASS {len(got)} words, capacity 256, full stall, pointer wraps')
if __name__=='__main__':unittest.main()

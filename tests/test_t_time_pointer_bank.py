"""All pointer classes, wrap, I=0 and interrupted reset; no SDRAM traffic."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TB=r'''
module tb;
reg clk=0;always #5 clk=~clk;
reg resetn=0,next_symbol=0;reg[14:0]lengths=0;reg[1:0]ql=0;reg[6:0]qc=0;
wire valid,busy;wire[10:0]position;
t_time_pointer_bank dut(clk,resetn,next_symbol,lengths,ql,qc,valid,position,busy);
integer epoch,symbol,l,c,len,depth,expected,checks=0;
task wait_ready;
 integer cycles;
 begin
  cycles=0;while(busy)begin @(negedge clk);cycles=cycles+1;if(cycles>289)$fatal(1,"busy stuck");end
 end
endtask
initial begin
 for(epoch=0;epoch<3;epoch=epoch+1)begin
  @(negedge clk);resetn=0;
  case(epoch)0:lengths={5'd16,5'd8,5'd4};1:lengths={5'd4,5'd2,5'd1};2:lengths=0;endcase
  repeat(2)@(negedge clk);resetn=1;wait_ready;
  for(symbol=0;symbol<(epoch==2?3:1525);symbol=symbol+1)begin
   for(l=0;l<3;l=l+1)for(c=0;c<96;c=c+1)begin
    ql=l;qc=c;#1;len=(lengths>>(l*5))&31;depth=len*(95-c);
    expected=depth==0?0:symbol%depth;
    if(!valid || position!==11'(expected))$fatal(1,"pointer mismatch ep=%0d sym=%0d layer=%0d cls=%0d got=%0d wanted=%0d",epoch,symbol,l,c,position,expected);
    checks=checks+1;@(negedge clk);
   end
   next_symbol=1;@(negedge clk);next_symbol=0;
   if(valid)$fatal(1,"query valid while updating");wait_ready;
  end
  // Reset partway through an update with old state still in the array.
  next_symbol=1;@(negedge clk);next_symbol=0;repeat(7)@(negedge clk);
 end
 $display("POINTER_CHECKS %0d",checks);$finish;
end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class PointerTest(unittest.TestCase):
 def test_all_classes_and_wrap(self):
  for source in ('experiments/t_time_pointer_bank.sv','experiments/t_time_pointer_bank_shift.sv'):
   with tempfile.TemporaryDirectory() as d:
    p=Path(d);(p/'tb.sv').write_text(TB)
    r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(ROOT/source),str(p/'tb.sv')],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stderr)
    r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=90)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('POINTER_CHECKS 879264',r.stdout)
    print(r.stdout)
if __name__=='__main__':unittest.main()

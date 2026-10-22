"""Queue oracle checks data retention, stalls, replacement, and read-only guard."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TB = r'''
module tb;
parameter RO=0;
reg clk=0;always #5 clk=~clk;
reg resetn=0,iv=0,iw=0,ready=0;
reg[20:0]ia=0;reg[255:0]id=0;reg[31:0]im=0;
wire ir,ov,ow,fault;wire[20:0]oa;wire[255:0]od;wire[31:0]om;
sdram_request_slot #(.READ_ONLY(RO)) dut(clk,resetn,iv,ir,iw,ia,id,im,
 ov,ready,ow,oa,od,om,fault);
reg occupied=0,ef=0,ew=0;reg[20:0]ea;reg[255:0]ed;reg[31:0]em;
reg pop,push;integer i,j,seed=407,accepted=0,completed=0,stalled=0,replaced=0;
initial begin
 for(i=0;i<6000;i=i+1)begin
  @(negedge clk);
  resetn=(i>2 && i!=3000 && i!=3001);
  iv=($random(seed)&3)!=0;ready=($random(seed)&7)<3;
  iw=($random(seed)&1);ia=$random(seed);im=$random(seed);
  for(j=0;j<8;j=j+1)id[j*32+:32]=$random(seed);
  #1;
  if(ir !== (resetn && (!occupied || ready) && (!RO || !iw)))$fatal(1,"ready");
  if(ov !== (resetn && occupied))$fatal(1,"valid");
  if(ov)begin
   if(oa!==ea || ow!==(RO ? 1'b0 : ew) ||
    od!==(RO ? 256'd0 : ed) || om!==(RO ? 32'd0 : em))$fatal(1,"descriptor");
  end
  pop=ov && ready;push=iv && ir;
  if(pop)completed=completed+1;
  if(push)accepted=accepted+1;
  if(ov && !ready)stalled=stalled+1;
  if(pop && push)replaced=replaced+1;
  @(posedge clk);
  if(!resetn)begin occupied=0;ef=0;end
  else begin
   if(iv && RO && iw)ef=1;
   if(pop)occupied=0;
   if(push)begin occupied=1;ea=ia;ew=iw;ed=id;em=im;end
  end
  #1;if(fault!==ef)$fatal(1,"fault/reset");
 end
 if(accepted<300 || completed<300 || stalled<300 || replaced<100)$fatal(1,"coverage");
 $display("PASS RO=%0d accepted=%0d completed=%0d stalls=%0d replacements=%0d",
 RO,accepted,completed,stalled,replaced);$finish;
end
endmodule
'''


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'), 'Icarus required')
class RequestSlotTest(unittest.TestCase):
    def test_read_write_and_read_only(self):
        for readonly in (0, 1):
            with self.subTest(readonly=readonly), tempfile.TemporaryDirectory() as d:
                p = Path(d)
                (p / 'tb.sv').write_text(TB)
                subprocess.run(['iverilog', '-g2012', '-s', 'tb', f'-Ptb.RO={readonly}',
                                '-o', str(p / 'sim'), str(p / 'tb.sv'),
                                str(ROOT / 'rtl/sdram_request_slot.sv')], check=True)
                result = subprocess.run(['vvp', str(p / 'sim')], text=True,
                                        capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PASS', result.stdout)
                print(result.stdout.strip())

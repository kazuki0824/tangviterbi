"""Cycle equivalence of registered refresh predicate, not physical timing proof."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'), 'Icarus required')
class RefreshPredecodeTest(unittest.TestCase):
    def test_cycle_equivalence(self):
        ports = '''.clk(clk),.resetn(resetn),.req_valid(valid),.req_write(wr),
          .req_address(addr),.req_data(payload),.req_dqm(mask),.rsp_ready(ready),
          .dq_in(din),.req_ready(o[0]),.rsp_valid(o[1]),.rsp_data(o[257:2]),
          .initialized(o[258]),.fault(o[259]),.sd_cmd(o[262:260]),
          .sd_bank(o[264:263]),.sd_address(o[275:265]),.sd_cke(o[276]),
          .sd_dqm(o[280:277]),.dq_oe(o[281]),.dq_out(o[313:282])'''
        instances = '\n'.join(
            f'{module} #(.INIT_CYCLES(3),.REFRESH_CYCLES(PERIOD)) {name}('
            + ports.replace('o[', f'{name}_o[') + ');'
            for module, name in [('dual_sdram_burst', 'old'), ('new_controller', 'revised')])
        tb = r'''module tb;
parameter PERIOD=1203;
reg clk=0;always #5 clk=~clk;
reg resetn=0,valid=0,wr=0,ready=1;
reg[20:0]addr=0;reg[255:0]payload=0;reg[31:0]mask=0,din=0;
wire[313:0]old_o,revised_o;
integer i,seed=124508,accepts=0,refreshes=0;
INSTANCES
task check;
begin
 #1;
 if(old_o!==revised_o || old.refresh_due!==revised.refresh_due)
  $fatal(1,"cycle mismatch period=%0d cycle=%0d",PERIOD,i);
end
endtask
initial begin
 for(i=0;i<4*PERIOD+20000;i=i+1)begin
  @(negedge clk);
  resetn=(i>3 && i!=13000 && i!=13001);
  // Hold requests until accepted, varying row/bank and response stalls.
  if(!valid || old_o[0])begin
   valid=($random(seed)&3)!=0;wr=$random(seed)&1;
   addr=($random(seed)&21'h1ffff8);payload={8{$random(seed)}};mask=$random(seed);
  end
  ready=($random(seed)&7)!=0;din=$random(seed);
  check;
  if(valid && old_o[0])accepts=accepts+1;
  if(old_o[262:260]==1)refreshes=refreshes+1;
  @(posedge clk);check;
 end
 // Deliberately prevent refresh to cover saturation and fault timing.
 force old.state=12;force revised.state=12;
 force old.wait_count=16'hffff;force revised.wait_count=16'hffff;
 repeat(PERIOD+10)begin @(posedge clk);check;end
 if(!old_o[259] || accepts==0 || refreshes<9)$fatal(1,"coverage");
 $display("PASS period=%0d accepts=%0d refreshes=%0d",PERIOD,accepts,refreshes);
 $finish;
end
endmodule
'''.replace('INSTANCES', instances)
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            (d/'new.sv').write_text((ROOT/'experiments/dual_sdram_refresh_predecode.sv').read_text().replace('module dual_sdram_burst', 'module new_controller'))
            (d/'tb.sv').write_text(tb)
            for period in (64, 1203, 65535):
                with self.subTest(period=period):
                    subprocess.run(['iverilog', '-g2012', '-s', 'tb', f'-Ptb.PERIOD={period}', '-o', str(d/'sim'), str(d/'tb.sv'), str(d/'new.sv'), str(ROOT/'rtl/dual_sdram_burst.sv')], check=True)
                    p = subprocess.run(['vvp', str(d/'sim')], text=True, capture_output=True, timeout=60)
                    self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
                    print(p.stdout, flush=True)

"""Pipelined exchange: independent byte/mask scoreboard with downstream stalls."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_dual_vector_exchange import BENCH, pin_bench
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class PipelinedExchange(unittest.TestCase):
    def run_bench(self, pin, pair=False):
        bench=(pin_bench() if pin else BENCH).replace('dual_vector_exchange dut','dual_vector_exchange_pipelined dut')
        # Output may be stalled while memory is overwritten: its old bytes have
        # already been copied into a dedicated register. Byte scoreboard checks
        # that these bytes survive subsequent writes and input capture.
        bench=bench.replace('  if(qw && got<sent)$fatal(1,"overwritten before output accepted");','')
        bench=bench.replace('if(!oe||got<sent)$fatal(1,"write before output");','if(!oe)$fatal(1,"missing write enable");')
        if pair:
            bench=bench.replace('dual_vector_exchange_pipelined dut','dual_vector_exchange_pipelined #(.WIDTH(16)) dut')
            bench=bench.replace('wire [7:0] id=(sent*17+trial*31);',"wire [15:0] id={8'((sent+1)*17+trial*31),8'(sent*17+trial*31)};")
            bench=bench.replace('wire [7:0] od;','wire [15:0] od;').replace('reg [7:0] os;','reg [15:0] os;')
            bench=bench.replace('sent<=sent+1','sent<=sent+2').replace('got<=got+1','got<=got+2')
            bench=bench.replace('od!==expected[got]','od!=={expected[got+1],expected[got]}')
            bench=bench.replace('trial<128','trial<64').replace('1024+trial%32','1024+(trial%16)*2')
            bench=bench.replace('case(trial/32)0:len=1;1:len=32;2:len=33;3:len=773;',
                                'case(trial/16)0:len=2;1:len=32;2:len=34;3:len=774;')
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/'tb.sv').write_text(bench)
            files=[ROOT/'rtl/dual_vector_exchange_pipelined.sv']
            if pin: files.append(ROOT/'rtl/dual_sdram_burst.sv')
            subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),*map(str,files)],check=True)
            r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn('PASS',r.stdout)
    def test_stalled_masked_exchange(self): self.run_bench(False)
    def test_pin_refresh_exchange(self): self.run_bench(True)

    def test_pair_stalls(self): self.run_bench(False, True)
    def test_pair_pin_refresh(self): self.run_bench(True, True)

"""Cycle-equivalence and existing ownership/priority contract for matrix selection."""
import shutil, subprocess, tempfile, unittest
from pathlib import Path
import test_sdram_client_arbiter_grace as grace
ROOT=Path(__file__).resolve().parents[1]

class ContractTest(grace.LeaseTest):
 rtl_file=ROOT/'experiments/sdram_client_arbiter_matrix.sv'

@unittest.skipUnless(shutil.which('yosys'), 'Yosys required')
class EquivalenceTest(unittest.TestCase):
 def test_sequential_equivalence(self):
  for suffix in ['', '_metadata']:
   with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as tmp:
    module='sdram_client_arbiter'+suffix
    script=f'''read_verilog -sv {ROOT}/experiments/sdram_client_arbiter_tile_grace{suffix}.sv
proc
memory
rename {module} gold
read_verilog -sv {ROOT}/experiments/sdram_client_arbiter_matrix{suffix}.sv
proc
memory
rename {module} gate
equiv_make gold gate equiv
hierarchy -top equiv
equiv_simple
equiv_induct -seq 4
equiv_status -assert
'''
    p=Path(tmp)/'check.ys';p.write_text(script)
    r=subprocess.run(['yosys','-Q','-s',str(p)],capture_output=True,text=True,timeout=120)
    print(r.stdout,flush=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)

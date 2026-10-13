"""Block-RAM RS storage: independent correction and bounded failure paths."""
from pathlib import Path
import json,subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from s3_rs_isdb import source

class CompactRSTest(unittest.TestCase):
 def test_independent_codewords_and_dirty_resets(self):
    out=ROOT/'build/s3-rs-compact';out.mkdir(parents=True,exist_ok=True)
    (out/'dut.sv').write_text(source(True,True))
    p=subprocess.run([sys.executable,str(ROOT/'experiments/check_isdb_rs.py'),'--rtl',str(out/'dut.sv'),
        '--output',str(out/'vectors.json'),'--max-cycles','2667'],capture_output=True,text=True,timeout=300)
    (out/'independent.log').write_text(p.stdout+p.stderr)
    self.assertEqual(p.returncode,0,p.stdout+p.stderr)
    r=json.loads((out/'vectors.json').read_text())
    self.assertTrue(r['all_pass']);self.assertEqual(r['total'],262)
    self.assertLessEqual(r['maximum_observed_cycles'],2667)
 def test_failure_paths_match_and_finish_on_time(self):
    out=ROOT/'build/s3-rs-compact-failures';out.mkdir(parents=True,exist_ok=True)
    old=source(True);new=source(True,True)
    (out/'reference.sv').write_text(old.replace('module rs204_188_compact','module rs204_188_compact_reference'))
    (out/'dut.sv').write_text(new[new.index('module rs204_188_compact'):])
    tb=(ROOT/'tests/rs_budget_tb.sv').read_text()
    # Only the Chien completion path acquires the extra synchronous prefetch
    # clock. All bytes and block_fail remain identical, including random
    # invalid words; >8 errors do not guarantee detectable failure for RS.
    (out/'tb.sv').write_text(tb)
    p=subprocess.run(['iverilog','-g2012','-s','rs_budget_tb','-Prs_budget_tb.MAX_CYCLES=2667',
        '-Prs_budget_tb.CHIEN_SAVING=-1','-o',str(out/'sim'),str(out/'reference.sv'),str(out/'dut.sv'),str(out/'tb.sv')],capture_output=True,text=True)
    self.assertEqual(p.returncode,0,p.stderr)
    p=subprocess.run(['vvp','sim'],cwd=out,capture_output=True,text=True,timeout=120)
    (out/'simulation.log').write_text(p.stdout+p.stderr)
    self.assertEqual(p.returncode,0,p.stdout+p.stderr);self.assertIn('PASS',p.stdout)
if __name__=='__main__':unittest.main()

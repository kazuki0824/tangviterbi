"""Execute C NOR switch acknowledgements independently of the Python model."""
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
class ModeSwitchTest(unittest.TestCase):
 def test_c_switch_actual_acknowledgements_and_fail_stop(self):
  out=ROOT/'build/s3-mode-switch';out.mkdir(parents=True,exist_ok=True)
  subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',
   '-Iexperiments','experiments/s3_mode_switch.c','tests/s3_mode_switch_host.c','-o',str(out/'sim')],cwd=ROOT,check=True)
  r=subprocess.run([str(out/'sim')],capture_output=True,text=True,timeout=10)
  (out/'simulation.log').write_text(r.stdout+r.stderr);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()

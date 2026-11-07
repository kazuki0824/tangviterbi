"""Every extended shared-core output lane is observed through the probe."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
from tests.test_sdram_probe_observation import TB
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ProbeTest(unittest.TestCase):
 def test_seven_outputs(self):
  tb=TB.replace('355','7').replace('354','6').replace('sdf_sdram_service_probe','shared_tc8_k7_probe')
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(tb)
   files=[p/'tb.sv',ROOT/'rtl/shared_k7_context.sv',*(ROOT/'experiments'/f for f in ('shared_tc8_k7_context.sv','shared_tc8_k7_boundary.sv','shared_tc8_k7_probe.sv'))]
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),*map(str,files)],check=True)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=20)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS all 7 lanes',r.stdout)

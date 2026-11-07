"""All four measured TC8PSK chain output lanes reach the signature."""
import shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from tests.test_sdram_probe_observation import TB
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from s3_tc8psk import source
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ProbeTest(unittest.TestCase):
 def test_all_chain_output_lanes(self):
  tb=TB.replace('355','4').replace('354','3').replace('sdf_sdram_service_probe','s_tc8psk_chain_probe')
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(tb);(p/'survivor.sv').write_text(source(True,True,22,True))
   files=[p/'tb.sv',p/'survivor.sv',ROOT/'experiments/s_tc8psk_chain_probe.sv',ROOT/'rtl/s_tc8psk_chain.sv',ROOT/'rtl/s3_tc8psk_metric_folded.sv']
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),*map(str,files)],check=True)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=20)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS all 4 lanes',r.stdout)

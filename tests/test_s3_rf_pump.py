"""Execute real adapter/pump/ring; only the SDK hardware boundary is simulated."""
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
class PumpTest(unittest.TestCase):
 def test_native_payload_credit_and_actual_DMA_ownership(self):
  out=ROOT/'build/s3-rf-pump';out.mkdir(parents=True,exist_ok=True)
  subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all',
   '-Itests/s3_sdk_shim','-Iexperiments','experiments/s3_transport.c','experiments/s3_spi_transport.c',
   'experiments/s3_rf_pump.c','tests/s3_rf_pump_host.c','-o',str(out/'sim')],cwd=ROOT,check=True)
  logs=[]
  for limit in (2,4):
   r=subprocess.run([str(out/'sim'),str(limit)],capture_output=True,text=True,timeout=30)
   logs.append(f'credit_limit={limit}\n'+r.stdout+r.stderr)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS 400 pages',r.stdout)
  (out/'simulation.log').write_text(''.join(logs))
if __name__=='__main__':unittest.main()

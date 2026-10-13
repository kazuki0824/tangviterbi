from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class ControlAdapterTest(unittest.TestCase):
 def test_driver_and_packet_parser(self):
  out=ROOT/'build/s3-control';out.mkdir(parents=True,exist_ok=True)
  subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-Itests/s3_sdk_shim','-Iexperiments','experiments/s3_transport.c','experiments/s3_spi_transport.c','experiments/s3_control.c','tests/s3_control_host.c','-o',str(out/'sim')],cwd=ROOT,check=True)
  r=subprocess.run([str(out/'sim')],text=True,capture_output=True,timeout=30)
  (out/'simulation.log').write_text(r.stdout+r.stderr);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()

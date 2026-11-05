from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class NativeClockTest(unittest.TestCase):
    def test_faults_stop_RF_before_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            exe=Path(temp)/'clock'
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-Iexperiments','tests/s3_native_clock_host.c','experiments/s3_capture_bridge.c','experiments/s3_transport.c','-o',str(exe)],cwd=ROOT,check=True)
            r=subprocess.run([str(exe)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(r.stdout)
if __name__=='__main__':unittest.main()

from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class NativePrepareBudgetTest(unittest.TestCase):
    def test_actual_partial_preparation_and_deadlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'test'
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-Iexperiments','tests/s3_native_prepare_budget_host.c','experiments/s3_capture_bridge.c','experiments/s3_transport.c','-o',str(binary)],cwd=ROOT,check=True)
            r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(r.stdout)

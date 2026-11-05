from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class SpanTest(unittest.TestCase):
    def test_contiguous_runs_and_every_declared_boundary_combination(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'span'
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-Iexperiments','experiments/s3_parallel_pack.c','tests/s3_parallel_span_host.c','-o',str(exe)],cwd=ROOT,check=True)
            r=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(r.stdout.strip())
if __name__=='__main__':unittest.main()

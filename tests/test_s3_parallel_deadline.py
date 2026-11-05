from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class ParallelDeadlineTest(unittest.TestCase):
    def test_clock_checked_before_final_publication_and_bank_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            exe=Path(directory)/'deadline'
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                            '-fsanitize=undefined','-fno-sanitize-recover=all','-Iexperiments',
                            'experiments/s3_parallel_pack.c','tests/s3_parallel_deadline_host.c',
                            '-o',str(exe)],cwd=ROOT,check=True)
            subprocess.run([str(exe)],check=True)
if __name__=='__main__':unittest.main()

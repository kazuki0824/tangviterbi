from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
class RawTasksTest(unittest.TestCase):
    def test_task_start_stop_and_watchdog_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory)/'tasks'
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                '-fsanitize=undefined','-fno-sanitize-recover=all','-pthread',
                '-DESP_PLATFORM','-Iexperiments','-Itests/s3_sdk_shim',
                'experiments/s3_raw_tasks.c','tests/s3_raw_tasks_host.c','-o',str(exe)],cwd=ROOT,check=True)
            subprocess.run([str(exe)],check=True,timeout=30)
if __name__ == '__main__': unittest.main()

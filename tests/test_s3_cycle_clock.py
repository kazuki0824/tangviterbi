from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CycleClockTest(unittest.TestCase):
    def test_calibration_intervals_and_actual_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / 'clock'
            subprocess.run([
                'cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=undefined', '-fno-sanitize-recover=all',
                '-DESP_PLATFORM', '-Iexperiments', '-Itests/s3_sdk_shim',
                'experiments/s3_cycle_clock.c', 'tests/s3_cycle_clock_host.c',
                '-o', str(exe)], cwd=ROOT, check=True)
            subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()

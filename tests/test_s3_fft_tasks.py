"""Execute the actual task adapter with two host threads and independent full FFT."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('simd_source',ROOT/'ci/s3_fft_simd_source.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
class TasksTest(unittest.TestCase):
 def test_real_task_adapter_ownership_stop_and_every_mode(self):
  out=ROOT/'build/s3-fft-tasks';out.mkdir(parents=True,exist_ok=True)
  (out/'oracle.c').write_text(source.host_source());(out/'tiles.c').write_text(source.host_tiled_source())
  subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-DESP_PLATFORM','-pthread',
   '-fwrapv','-fno-strict-aliasing','-fsanitize=undefined','-fno-sanitize-recover=all',
   '-Itests/s3_sdk_shim','-Iexperiments','experiments/s3_fft_worker.c','experiments/s3_fft_tasks.c',
   'experiments/s3_fft_simd_tiles.c','experiments/s3_fft_simd.c','experiments/s3_fft_tiles.c',
   str(out/'oracle.c'),str(out/'tiles.c'),'tests/s3_freertos_host.c','tests/s3_fft_tasks_host.c','-o',str(out/'sim')],cwd=ROOT,check=True)
  r=subprocess.run([str(out/'sim')],capture_output=True,text=True,timeout=30)
  (out/'simulation.log').write_text(r.stdout+r.stderr)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  self.assertIn('PASS actual task adapter',r.stdout)
if __name__=='__main__':unittest.main()

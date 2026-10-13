"""Actual SPI/worker adapters; SDK silicon boundary replaced by deterministic completions."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('simd_source',ROOT/'ci/s3_fft_simd_source.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
class ExchangeTest(unittest.TestCase):
 def test_full_DMA_frame_lifetime_all_modes(self):
  out=ROOT/'build/s3-fft-exchange';out.mkdir(parents=True,exist_ok=True)
  (out/'oracle.c').write_text(source.host_source());(out/'tiles.c').write_text(source.host_tiled_source())
  subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-DESP_PLATFORM','-pthread',
   '-fwrapv','-fno-strict-aliasing','-fsanitize=undefined','-fno-sanitize-recover=all',
   '-Itests/s3_sdk_shim','-Iexperiments','experiments/s3_transport.c','experiments/s3_spi_transport.c',
   'experiments/s3_fft_worker.c','experiments/s3_fft_tasks.c','experiments/s3_fft_exchange.c',
   'experiments/s3_fft_simd_tiles.c','experiments/s3_fft_simd.c','experiments/s3_fft_tiles.c',
   str(out/'oracle.c'),str(out/'tiles.c'),'tests/s3_freertos_host.c','tests/s3_fft_exchange_host.c','-o',str(out/'sim')],cwd=ROOT,check=True)
  r=subprocess.run([str(out/'sim')],capture_output=True,text=True,timeout=45)
  (out/'simulation.log').write_text(r.stdout+r.stderr)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS actual SPI/task exchange',r.stdout)
if __name__=='__main__':unittest.main()

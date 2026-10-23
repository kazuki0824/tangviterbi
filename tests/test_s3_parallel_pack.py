"""Two live pthread workers, actual C packing, adversarial coordinator/DMA order."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class ParallelPackTest(unittest.TestCase):
    def test_concurrent_lossless_ownership_and_negative_boundaries(self):
        with tempfile.TemporaryDirectory() as temp:
            exe=Path(temp)/'host'
            subprocess.run(['cc','-std=c11','-O2','-g','-Wall','-Wextra','-Werror',
                '-fsanitize=undefined','-fno-sanitize-recover=all','-pthread','-Iexperiments',
                'experiments/s3_parallel_pack.c','tests/s3_parallel_pack_host.c','-o',str(exe)],cwd=ROOT,check=True)
            for banks in (1,2,17,2000):
                with self.subTest(banks=banks):
                    run=subprocess.run([str(exe),str(banks)],capture_output=True,text=True,timeout=120)
                    self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                    print(run.stdout.strip())
    def test_native_bank_handoff_and_stalled_worker_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            exe=Path(temp)/'capture'
            sources=['s3_parallel_pack.c','s3_parallel_capture.c','s3_native_capture.c',
                     's3_capture_bridge.c','s3_transport.c']
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                '-fsanitize=undefined','-fno-sanitize-recover=all','-Iexperiments']+
                ['experiments/'+x for x in sources]+['tests/s3_parallel_capture_host.c','-o',str(exe)],cwd=ROOT,check=True)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=120)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            print(run.stdout.strip())
    def test_bulk_SPI_lease_adapter_and_queue_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            exe=Path(temp)/'spi'
            sources=['s3_parallel_pack.c','s3_parallel_spi.c','s3_spi_transport.c','s3_transport.c']
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                '-fsanitize=undefined','-fno-sanitize-recover=all','-Iexperiments','-Itests/s3_sdk_shim']+
                ['experiments/'+x for x in sources]+['tests/s3_parallel_spi_host.c','-o',str(exe)],cwd=ROOT,check=True)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=120)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            print(run.stdout.strip())
if __name__=='__main__':unittest.main()

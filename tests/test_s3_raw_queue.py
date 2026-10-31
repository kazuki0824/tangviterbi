import subprocess,tempfile,unittest
from pathlib import Path
from experiments.s3_joint_runtime import ROOT
class RawQueue(unittest.TestCase):
 def test_depth_two_ownership_and_faults(self):
  with tempfile.TemporaryDirectory() as tmp:
   for chunk in (16384,32768):
    exe=Path(tmp)/'queue'
    subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=undefined','-fno-sanitize-recover=all',f'-DS3_RAW_TRANSFER_BYTES={chunk}','-Iexperiments','-Itests/s3_sdk_shim','experiments/s3_raw_queue.c','experiments/s3_parallel_pack.c','tests/s3_raw_queue_host.c','-o',str(exe)],cwd=ROOT,check=True)
    subprocess.run([str(exe)],check=True)
if __name__=='__main__':unittest.main()

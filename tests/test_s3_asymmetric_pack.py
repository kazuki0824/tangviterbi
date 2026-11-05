"""Actual unequal C partition: concurrent output, ownership and RF handoff."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class AsymmetricPackTest(unittest.TestCase):
    def test_candidate_concurrent_streams_and_native_handoff(self):
        for share in (5,6,7):
            with self.subTest(core0_sixteenths=share),tempfile.TemporaryDirectory() as temp:
                for name,sources in (
                    ('concurrent',['experiments/s3_parallel_pack.c','tests/s3_parallel_pack_host.c']),
                    ('native',['experiments/'+s for s in ('s3_parallel_pack.c','s3_parallel_capture.c','s3_native_capture.c','s3_cycle_clock.c','s3_capture_bridge.c','s3_transport.c')]+['tests/s3_parallel_capture_host.c'])):
                    exe=str(Path(temp)/name)
                    subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pthread','-fsanitize=undefined','-fno-sanitize-recover=all','-Iexperiments',f'-DS3_PP_CORE0_SIXTEENTHS={share}',*sources,'-o',exe],cwd=ROOT,check=True)
                    r=subprocess.run([exe,'2000'] if name=='concurrent' else [exe],capture_output=True,text=True,timeout=120)
                    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                    print(share,name,r.stdout.strip())
    def test_response_model_uses_unequal_bank_work(self):
        from experiments.s3_worker_response import worker
        config=dict(release_delay=0,clock_error=0,ordinary_iteration=1,sampled_slice=1,slice_bound=1,older_banks=0,slice_pairs=512,events=[])
        for share,wanted in ((8,[8,8]),(7,[7,8]),(6,[6,9]),(5,[5,10])):
            actual=[worker(40,config,core0_sixteenths=share,worker_id=w)['max_slices_per_bank'] for w in (0,1)]
            self.assertEqual(actual,wanted)
        with self.assertRaises(ValueError):worker(40,config,core0_sixteenths=5)

"""Actual two-core worker/barrier with ANSI tile arithmetic; no SIMD/WCET claim."""
import concurrent.futures
import ctypes
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('simd_source',ROOT/'ci/s3_fft_simd_source.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)

class WorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();d=Path(cls.tmp.name)
        (d/'oracle.c').write_text(source.host_source())
        (d/'tiles.c').write_text(source.host_tiled_source())
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
            '-fwrapv','-fno-strict-aliasing','-fPIC','-shared',
            '-fsanitize=undefined','-fno-sanitize-recover=undefined','-Iexperiments',
            'tests/s3_fft_worker_host.c','experiments/s3_fft_worker.c',
            'experiments/s3_fft_simd.c','experiments/s3_fft_simd_tiles.c',
            'experiments/s3_fft_tiles.c',str(d/'oracle.c'),str(d/'tiles.c'),
            '-o',str(d/'worker.so')],cwd=ROOT,check=True)
        cls.lib=ctypes.CDLL(str(d/'worker.so'));cls.ptr=ctypes.POINTER(ctypes.c_int16)
        cls.lib.worker_create.argtypes=[cls.ptr,cls.ptr,ctypes.c_int,ctypes.c_uint,ctypes.c_int]
        cls.lib.worker_create.restype=ctypes.c_void_p
        for n in ('worker_step','worker_progress','worker_polls'):
            getattr(cls.lib,n).argtypes=[ctypes.c_void_p,ctypes.c_uint]
        for n in ('worker_destroy','worker_ready','worker_calls'):
            getattr(cls.lib,n).argtypes=[ctypes.c_void_p]
        cls.lib.s3_fft_simd_run.argtypes=[cls.ptr,cls.ptr,ctypes.c_void_p]
        cls.lib.s3_fft_reverse_tile.argtypes=[cls.ptr,*([ctypes.c_uint]*3)]
        cls.table=(ctypes.c_int16*8192).in_dll(cls.lib,'s3_fft_simd_table')
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def create(self,data,fail_core=-1,fail_poll=0,tile_fail=0):
        f=self.lib.worker_create(data.ctypes.data_as(self.ptr),self.table,fail_core,fail_poll,tile_fail)
        self.assertTrue(f);self.addCleanup(self.lib.worker_destroy,f);return f
    def test_actual_worker_two_threads_preserves_every_bin(self):
        rows=[];rng=np.random.default_rng(9813)
        for name,data in [('random',rng.integers(-8000,8000,16384,dtype=np.int16)),
                          ('extremes',rng.choice(np.array([-32768,-1,0,32767],dtype=np.int16),16384))]:
            gold=data.copy();f=self.create(data)
            self.assertEqual(self.lib.s3_fft_simd_run(gold.ctypes.data_as(self.ptr),self.table,None),0)
            def work(core):
                for _ in range(100000):
                    r=self.lib.worker_step(f,core)
                    self.assertIn(r,(0,1,2))
                    if r==2:return
                self.fail('worker failed to complete finite test')
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                jobs=[pool.submit(work,c) for c in (0,1)]
                for job in jobs:job.result(timeout=20)
            self.assertTrue(self.lib.worker_ready(f))
            self.assertEqual(self.lib.worker_calls(f),13*64)
            self.lib.s3_fft_reverse_tile(data.ctypes.data_as(self.ptr),8192,0,8192)
            np.testing.assert_array_equal(data,gold)
            rows.append(dict(input=name,all_complex_bins=8192,ANSI_matches=True,
                             tile_calls=832,service_calls=[self.lib.worker_polls(f,c) for c in (0,1)]))
        p=ROOT/'build/s3-fft-worker/result.json';p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(dict(scope=__doc__,cases=rows,real_RTOS_executed=False,
            SIMD_executed=False,CPU_WCET_verified=False,receiver_adopted=False),indent=2)+'\n')
    def test_lagging_peer_returns_and_services_RF_without_next_stage(self):
        data=np.zeros(16384,dtype=np.int16);f=self.create(data)
        for _ in range(32):self.assertEqual(self.lib.worker_step(f,0),1)
        self.assertEqual(self.lib.worker_progress(f,0),512)
        before=self.lib.worker_polls(f,0)
        for _ in range(200):self.assertEqual(self.lib.worker_step(f,0),0)
        self.assertEqual(self.lib.worker_polls(f,0)-before,400)
        self.assertEqual(self.lib.worker_calls(f),32)
        self.assertFalse(self.lib.worker_ready(f))
        for _ in range(32):self.assertEqual(self.lib.worker_step(f,1),1)
        self.assertEqual(self.lib.worker_step(f,0),1)
        self.assertEqual(self.lib.worker_progress(f,0),528)
    def test_RF_and_tile_failures_never_release_frame(self):
        for poll,tile_fail,expected_calls in [(1,0,0),(2,0,1),(0,1,1)]:
            data=np.zeros(16384,dtype=np.int16)
            f=self.create(data,0,poll,tile_fail)
            self.assertEqual(self.lib.worker_step(f,0),-1)
            self.assertEqual(self.lib.worker_step(f,1),-1)
            self.assertEqual(self.lib.worker_calls(f),expected_calls)
            self.assertFalse(self.lib.worker_ready(f))
    def test_bad_frame_or_owner_is_rejected(self):
        data=np.zeros(16384,dtype=np.int16);p=data.ctypes.data_as(self.ptr)
        self.assertFalse(self.lib.worker_create(p,p,-1,0,0))
        self.assertFalse(self.lib.worker_create(None,self.table,-1,0,0))
        f=self.create(data)
        self.assertEqual(self.lib.worker_step(f,2),-1)
        self.assertEqual(self.lib.worker_calls(f),0)
    def test_last_RF_service_failure_does_not_publish_completion(self):
        data=np.zeros(16384,dtype=np.int16);f=self.create(data,0,832)
        for _ in range(415):
            self.assertEqual(self.lib.worker_step(f,0),1)
            self.assertEqual(self.lib.worker_step(f,1),1)
        self.assertEqual(self.lib.worker_step(f,0),-1)
        self.assertEqual(self.lib.worker_progress(f,0),13*512-16)
        self.assertFalse(self.lib.worker_ready(f))
        self.assertEqual(self.lib.worker_step(f,1),-1)

if __name__=='__main__':unittest.main()

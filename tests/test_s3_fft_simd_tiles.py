"""Parallel tile ownership/order tests using ANSI arithmetic, not target SIMD execution."""
import concurrent.futures,ctypes,importlib.util,json,random,subprocess,tempfile,threading,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('simd_source',ROOT/'ci/s3_fft_simd_source.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
class TilesTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();d=Path(cls.tmp.name)
  (d/'oracle.c').write_text(source.host_source());(d/'tiles.c').write_text(source.host_tiled_source())
  subprocess.run(['gcc','-std=c11','-O2','-fwrapv','-fno-strict-aliasing','-fPIC','-shared',
   '-fsanitize=undefined','-fno-sanitize-recover=undefined','experiments/s3_fft_simd.c',
   'experiments/s3_fft_simd_tiles.c','experiments/s3_fft_tiles.c',str(d/'oracle.c'),str(d/'tiles.c'),
   '-o',str(d/'lib.so')],cwd=ROOT,check=True)
  cls.lib=ctypes.CDLL(str(d/'lib.so'));cls.ptr=ctypes.POINTER(ctypes.c_int16)
  cls.lib.s3_fft_simd_tile.argtypes=[cls.ptr,cls.ptr,*([ctypes.c_uint]*3)]
  cls.lib.s3_fft_simd_run.argtypes=[cls.ptr,cls.ptr,ctypes.c_void_p]
  cls.lib.s3_fft_reverse_tile.argtypes=[cls.ptr,*([ctypes.c_uint]*3)]
  cls.table=(ctypes.c_int16*8192).in_dll(cls.lib,'s3_fft_simd_table')
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_parallel_disjoint_blocks_and_stage_barriers(self):
  rng=np.random.default_rng(8512);rows=[]
  for name,signal in [('random',rng.integers(-8000,8000,16384,dtype=np.int16)),
   ('extremes',rng.choice(np.array([-32768,-32767,-1,0,1,32767],dtype=np.int16),16384)),
   ('zeros',np.zeros(16384,dtype=np.int16))]:
   data=signal.copy();gold=signal.copy();barrier=threading.Barrier(2)
   dp=data.ctypes.data_as(self.ptr)
   self.assertEqual(self.lib.s3_fft_simd_run(gold.ctypes.data_as(self.ptr),self.table,None),0)
   def worker(core):
    for stage in range(13):
     randomizer=random.Random(core*100+stage);chunks=[];start=512*core
     while start<512*(core+1):
      count=min(randomizer.randrange(1,17),512*(core+1)-start);chunks.append((start,count));start+=count
     randomizer.shuffle(chunks)
     for start,count in chunks:self.assertEqual(self.lib.s3_fft_simd_tile(dp,self.table,stage,start,count),0)
     barrier.wait(timeout=5)
   with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    jobs=[pool.submit(worker,c) for c in (0,1)]
    for job in jobs:job.result(timeout=10)
   bit_reversed=data.copy()
   self.lib.s3_fft_reverse_tile(dp,8192,0,8192)
   np.testing.assert_array_equal(data,gold)
   for i in [0,1,7,1023,1024,4095,8191]:
    natural=int(f'{i:013b}'[::-1],2)
    np.testing.assert_array_equal(bit_reversed[2*i:2*i+2],gold[2*natural:2*natural+2])
   rows.append(dict(input=name,outputs=8192,parallel_ANSI_matches_full_ANSI=True))
  p=ROOT/'build/s3-fft-simd/tile-host-oracle.json'
  p.parent.mkdir(parents=True,exist_ok=True)
  p.write_text(json.dumps(dict(scope=__doc__,cases=rows,maximum_butterflies_per_tile=64,
   SIMD_executed=False,SIMD_ANSI_bit_equivalence_verified=False,CPU_WCET_verified=False),indent=2)+'\n')
 def test_invalid_range_does_not_change_data(self):
  data=np.zeros(16384,dtype=np.int16);dp=data.ctypes.data_as(self.ptr)
  for stage,start,count in [(13,0,1),(0,0,0),(0,0,17),(12,1024,1),(7,1020,8)]:
   self.assertEqual(self.lib.s3_fft_simd_tile(dp,self.table,stage,start,count),-1)
  self.assertFalse(np.any(data))
 def test_derived_loops_use_pinned_arithmetic(self):
  text=source.tiled_source()
  self.assertEqual(text.count('ee.cmul.s16'),6)
  for name in ('general','pair','final'):self.assertIn('.global s3_fft_simd_'+name,text)

if __name__=='__main__':unittest.main()

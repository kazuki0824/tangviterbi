"""Test the pinned coefficient/order adapter with upstream ANSI, not SIMD execution."""
import ctypes,importlib.util,json
from pathlib import Path
import subprocess,tempfile,unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('simd_source',ROOT/'ci/s3_fft_simd_source.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)

class SIMDAdapterTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();d=Path(cls.tmp.name)
  (d/'oracle.c').write_text(source.host_source())
  subprocess.run(['gcc','-std=c11','-O2','-fwrapv','-fno-strict-aliasing','-fPIC','-shared',
   '-fsanitize=undefined','-fno-sanitize-recover=undefined','experiments/s3_fft_simd.c',
   'experiments/s3_fft_tiles.c',str(d/'oracle.c'),'-o',str(d/'lib.so')],cwd=ROOT,check=True)
  cls.lib=ctypes.CDLL(str(d/'lib.so'));cls.ptr=ctypes.POINTER(ctypes.c_int16)
  cls.lib.s3_fft_simd_run.argtypes=[cls.ptr,cls.ptr,ctypes.c_void_p]
  cls.table=(ctypes.c_int16*8192).in_dll(cls.lib,'s3_fft_simd_table')
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_coefficient_order_and_full_size(self):
  self.assertEqual((ROOT/'experiments/s3_fft_simd_coefficients.inc').read_text(),source.coefficients())
  self.assertEqual(ctypes.sizeof(self.table),16384)
  for j in range(4096):
   k=int(f'{j:012b}'[::-1],2);angle=2*np.pi*k/8192
   self.assertEqual((self.table[2*j],self.table[2*j+1]),
    (int(32767*np.cos(angle)),int(32767*np.sin(angle))),j)
 def test_natural_order_against_fft_without_discarding_bins(self):
  n=8192;t=np.arange(n);rng=np.random.default_rng(31713)
  cases=dict(zero=np.zeros(n,dtype=complex),DC=np.full(n,1000+2000j),
   impulse=np.r_[12000+6000j,np.zeros(n-1)],
   tone=np.rint(4000*np.cos(2*np.pi*7*t/n))+1j*np.rint(4000*np.sin(2*np.pi*7*t/n)),
   noise=rng.integers(-8000,8000,n)+1j*rng.integers(-8000,8000,n))
  rows=[]
  for name,signal in cases.items():
   data=np.empty(2*n,dtype=np.int16);data[::2]=signal.real;data[1::2]=signal.imag
   self.assertEqual(data.ctypes.data%16,0)
   self.assertEqual(self.lib.s3_fft_simd_run(data.ctypes.data_as(self.ptr),self.table,None),0)
   got=data[::2].astype(float)+1j*data[1::2].astype(float)
   error=float(np.max(np.abs(got-np.fft.fft(signal)/n)))
   self.assertLessEqual(error,8,(name,error));rows.append(dict(input=name,bins=len(got),maximum_complex_error_LSB=error))
  out=ROOT/'build/s3-fft-simd';out.mkdir(exist_ok=True)
  (out/'host-oracle.json').write_text(json.dumps(dict(scope=__doc__,cases=rows,
   SIMD_executed=False,SIMD_ANSI_bit_equivalence_verified=False,CPU_WCET_verified=False),indent=2)+'\n')
 def test_bad_pointer_rejected_before_kernel(self):
  data=(ctypes.c_int16*16392)();base=ctypes.addressof(data)
  good=(base+15)&~15
  for d,t in [(0,ctypes.addressof(self.table)),(good+2,ctypes.addressof(self.table)),(good,good)]:
   self.assertEqual(self.lib.s3_fft_simd_run(ctypes.cast(d,self.ptr),ctypes.cast(t,self.ptr),None),-1)
 def test_upstream_hash_and_assembly_has_simd(self):
  generated=source.source()
  self.assertIn('ee.cmul.s16',generated);self.assertIn('.section .iram1',generated)

if __name__=='__main__':unittest.main()

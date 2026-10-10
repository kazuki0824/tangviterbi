"""Independent codeword checks for CPU RS partition exploration; no WCET claim."""
import ctypes as c,hashlib,json,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from check_isdb_rs import vectors,gf
class Tables(c.Structure):
 _fields_=[('exp',c.c_uint8*512),('log',c.c_uint8*256),('step',(c.c_uint8*256)*8)]+[(n,c.c_uint32) for n in ('mul_calls','mul_nonzero','div_calls','chien_steps')]
class Solution(c.Structure):
 _fields_=[('lambda_',c.c_uint8*17),('omega',c.c_uint8*16),('degree',c.c_uint8)]
def profile(t):return {n:getattr(t,n) for n in ('mul_calls','mul_nonzero','div_calls','chien_steps')}
def difference(a,b):return {k:a[k]-b[k] for k in a}
class OffloadTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  # A second test module reuses this oracle in the same unittest process.
  # Rewriting an mmap'ed shared object would corrupt the loaded library.
  if hasattr(cls,'lib'):return
  cls.out=ROOT/'build/s3-rs-offload';cls.out.mkdir(parents=True,exist_ok=True)
  subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fPIC','-shared','-DS3_RS_PROFILE',
   '-I'+str(ROOT/'experiments'),str(ROOT/'experiments/s3_rs_offload.c'),'-o',str(cls.out/'solver.so')],check=True)
  cls.lib=c.CDLL(str(cls.out/'solver.so'))
  cls.lib.s3_rs_tables_init.argtypes=[c.POINTER(Tables)]
  cls.lib.s3_rs_solve.argtypes=[c.POINTER(Tables),c.POINTER(c.c_uint8),c.POINTER(Solution)]
  cls.lib.s3_rs_chien.argtypes=[c.POINTER(Tables),c.POINTER(Solution),c.POINTER(c.c_uint8)]
  cls.lib.s3_rs_magnitudes.argtypes=[c.POINTER(Tables),c.POINTER(Solution),c.POINTER(c.c_uint8),c.c_uint,c.POINTER(c.c_uint8)]
 def test_independent_262_codewords_and_reused_workspace(self):
  t=Tables();s=Solution();pos=(c.c_uint8*8)();mag=(c.c_uint8*8)();self.lib.s3_rs_tables_init(c.byref(t))
  rows=[]
  for name,received,payload in vectors():
   syndrome=[];root=1
   for n in range(16):
    v=0
    for byte in received:v=gf(v,root)^byte
    syndrome.append(v);root=gf(root,2)
   start=profile(t)
   self.assertEqual(self.lib.s3_rs_solve(c.byref(t),(c.c_uint8*16)(*syndrome),c.byref(s)),1,name)
   after_bm=profile(t);count=self.lib.s3_rs_chien(c.byref(t),c.byref(s),pos)
   self.assertGreaterEqual(count,0,name);after_chien=profile(t)
   self.assertEqual(self.lib.s3_rs_magnitudes(c.byref(t),c.byref(s),pos,count,mag),1,name)
   result=received.copy()
   for n in range(count):result[pos[n]]^=mag[n]
   self.assertEqual(result[:188],payload,name)
   # Check parity bytes too, and every reported correction location/magnitude.
   from check_isdb_rs import encode
   original=encode(payload);self.assertEqual(result,original,name)
   expected=[(i,x^y) for i,(x,y) in enumerate(zip(received,original)) if x!=y]
   self.assertEqual([(pos[i],mag[i]) for i in range(count)],expected,name)
   if count:
    bad=(c.c_uint8*8)(*list(pos));bad[0]=204
    self.assertEqual(self.lib.s3_rs_magnitudes(c.byref(t),c.byref(s),bad,count,mag),0)
   rows.append(dict(case=name,errors=count,bm_omega=difference(after_bm,start),
      chien=difference(after_chien,after_bm),forney_with_locator_validation=difference(profile(t),after_chien)))
  result=dict(passed=len(rows),total=262,tables_bytes=c.sizeof(Tables),solution_bytes=c.sizeof(Solution),
   receiver_adopted=False,silicon_WCET_verified=False,
   scope='host C algorithm and operation counts; no target compile, RF/RTOS/SPI or FPGA split implementation',
   source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'experiments/s3_rs_offload.c',ROOT/'experiments/s3_rs_offload.h')},tests=rows)
  (self.out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':unittest.main()

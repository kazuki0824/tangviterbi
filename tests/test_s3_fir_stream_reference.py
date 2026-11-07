import ctypes as C
import random
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class State(C.Structure):
    _fields_=[('i',C.c_int16*33),('q',C.c_int16*33)]+[(x,C.c_uint32) for x in ('up','down','taps','phase','skip','head')]
class StreamTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); path=Path(cls.tmp.name)/'stream.so'
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',str(ROOT/'experiments/s3_fir_stream_reference.c'),'-o',str(path)],check=True)
        cls.lib=C.CDLL(str(path)); cls.init=cls.lib.s3_fir_stream_init; cls.push=cls.lib.s3_fir_stream_push
        cls.init.argtypes=[C.POINTER(State),C.c_uint32,C.c_uint32,C.c_uint32]
        cls.push.argtypes=[C.POINTER(State),C.c_uint32,C.POINTER(C.c_int16),C.POINTER(C.c_int32),C.POINTER(C.c_int32)]
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def test_complete_phase_cycles_across_bank_boundaries(self):
        rng=random.Random(94)
        for up,down,taps in [(32,63,32),(1443,2000,16),(1,1,33)]:
            n=down*3+35
            iv=[rng.randrange(-512,512) for _ in range(n)]; qv=[rng.randrange(-512,512) for _ in range(n)]
            cv=[rng.randrange(-32768,32768) for _ in range(up*taps)]
            coeff=(C.c_int16*len(cv))(*cv); s=State(); self.assertEqual(self.init(C.byref(s),up,down,taps),1)
            actual=[]; phases=set(); pos=0
            # Keep state across caller chunks, including one-word and nonaligned banks.
            while pos<n:
                end=min(n,pos+rng.choice([1,7,31,128,3072]))
                for index in range(pos,end):
                    a=C.c_int32(123);b=C.c_int32(456);phase=s.phase
                    produced=self.push(C.byref(s),(iv[index]&1023)|((qv[index]&1023)<<10)|(rng.randrange(4096)<<20),coeff,C.byref(a),C.byref(b))
                    if produced: actual.append((index,a.value,b.value));phases.add(phase)
                    else: self.assertEqual((a.value,b.value),(123,456))
                pos=end
            expected=[];m=0
            while m*down//up<n:
                newest=m*down//up;p=m*down%up
                expected.append((newest,*[sum(v[newest-k]*cv[p*taps+k] for k in range(taps) if newest>=k) for v in (iv,qv)]));m+=1
            self.assertEqual(actual,expected);self.assertEqual(len(phases),up)
    def test_int32_extremes(self):
        for sample in (-512,511):
            for coef in (-32768,32767):
                s=State();self.init(C.byref(s),1,1,33);c=(C.c_int16*33)(*([coef]*33));a=C.c_int32();b=C.c_int32()
                for count in range(1,67):
                    self.assertEqual(self.push(C.byref(s),(sample&1023)|((sample&1023)<<10),c,C.byref(a),C.byref(b)),1)
                    self.assertEqual((a.value,b.value),(min(count,33)*sample*coef,)*2)
    def test_reject_invalid_initialization(self):
        for args in [(0,1,16),(2,1,16),(1,1,0),(1,1,34),(1,2**32-1,16)]:
            s=State();s.head=99
            self.assertEqual(self.init(C.byref(s),*args),0);self.assertEqual(s.head,99)
if __name__=='__main__': unittest.main()

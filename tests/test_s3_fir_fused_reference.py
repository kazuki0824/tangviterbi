import ctypes,json,random,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class FusedFIRTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();out=Path(cls.tmp.name)/'fused.so'
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',str(ROOT/'experiments/s3_fir_fused_reference.c'),'-o',str(out)],check=True)
        cls.lib=ctypes.CDLL(str(out));cls.fn=cls.lib.s3_fir_fused_reference
        cls.fn.argtypes=[ctypes.POINTER(ctypes.c_uint32),ctypes.POINTER(ctypes.c_int16),ctypes.c_size_t,ctypes.POINTER(ctypes.c_int64),ctypes.POINTER(ctypes.c_int64)]
        cls.fn.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def evaluate(self,words,coeff):
        i=ctypes.c_int64();q=ctypes.c_int64()
        self.assertEqual(self.fn((ctypes.c_uint32*len(words))(*words),(ctypes.c_int16*len(coeff))(*coeff),len(words),ctypes.byref(i),ctypes.byref(q)),1)
        return i.value,q.value
    def test_every_component_code_and_metadata(self):
        for code in range(1024):
            signed=code if code<512 else code-1024
            for meta in (0,4095):
                self.assertEqual(self.evaluate([code|(code<<10)|(meta<<20)],[-32768]),(signed*-32768,)*2)
    def test_all_phase_layouts_against_separate_unpack(self):
        rng=random.Random(77);total=0
        for up,taps in [(32,32),(1443,16)]:
            for delta in (-1,0,1):
                n=up*taps+delta
                proto=[rng.randrange(-32768,32768) for _ in range(n)]
                for phase in range(up):
                    coeff=proto[phase::up];iv=[rng.randrange(-512,512) for _ in coeff];qv=[rng.randrange(-512,512) for _ in coeff]
                    words=[(i&1023)|((q&1023)<<10)|(rng.randrange(4096)<<20) for i,q in zip(iv,qv)]
                    with self.subTest(up=up,delta=delta,phase=phase):
                        self.assertEqual(self.evaluate(words,coeff),(sum(i*c for i,c in zip(iv,coeff)),sum(q*c for q,c in zip(qv,coeff))))
                    total+=1
        self.assertEqual(total,4425)
    def test_extremes_and_invalid_calls(self):
        self.assertEqual(self.evaluate([512|(511<<10)]*33,[-32768]*33),(512*32768*33,-511*32768*33))
        w=(ctypes.c_uint32*34)();c=(ctypes.c_int16*34)();i=ctypes.c_int64(123);q=ctypes.c_int64(456)
        for count in (0,34):
            self.assertEqual(self.fn(w,c,count,ctypes.byref(i),ctypes.byref(q)),0)
            self.assertEqual((i.value,q.value),(123,456))
        self.assertEqual(self.fn(w,c,1,ctypes.byref(i),ctypes.byref(i)),0)
        self.assertEqual(self.fn(None,c,1,ctypes.byref(i),ctypes.byref(q)),0)
if __name__=='__main__':unittest.main()

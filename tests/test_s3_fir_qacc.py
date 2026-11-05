import ctypes as C
import hashlib,json,math,random,subprocess,tempfile,unittest
from pathlib import Path
from experiments.s3_fir_accx_model import instructions
from experiments.s3_fir_qacc_model import execute
ROOT=Path(__file__).resolve().parents[1];DIR=ROOT/'reports/s3-preprocess-break-even/qacc'
class QaccTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();path=Path(cls.tmp.name)/'prepare.so'
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',str(ROOT/'experiments/s3_fir_qacc_prepare.c'),'-o',str(path)],check=True)
        cls.lib=C.CDLL(str(path));cls.prepare=cls.lib.s3_fir_qacc_prepare
        ptr=C.POINTER(C.c_int16)
        cls.prepare.argtypes=[ptr,ptr,C.c_size_t,ptr,C.c_uint32,C.c_uint32,C.c_uint32,C.c_uint32,ptr,ptr]
        cls.dis=(DIR/'qacc.dis').read_text()
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_source_and_disassembly_audit(self):
        r=json.loads((DIR/'qacc-audit.json').read_text())
        self.assertEqual(r['source_sha256'],hashlib.sha256((ROOT/'experiments/s3_fir_qacc.S').read_bytes()).hexdigest())
        self.assertEqual(r['disassembly_sha256'],hashlib.sha256((DIR/'qacc.dis').read_bytes()).hexdigest())
        self.assertTrue(all(c['passed'] for c in r['checks']))
    def test_all_batch_phase_groups_through_real_c_gather(self):
        rng=random.Random(75)
        for up,down,k in [(32,63,32),(1443,2000,16)]:
            groups=up//math.gcd(up,4);size=(groups*4+3)*down//up+1
            iv=[rng.randrange(-512,512) for _ in range(size)];qv=[rng.randrange(-512,512) for _ in range(size)]
            cv=[rng.randrange(-32768,32768) for _ in range(up*k)]
            i=(C.c_int16*size)(*iv);q=(C.c_int16*size)(*qv);c=(C.c_int16*len(cv))(*cv)
            samples=(C.c_int16*(8*k))();coeff=(C.c_int16*(8*k))();phases=set()
            code=instructions(self.dis,'s3_fir_qacc_'+str(k))
            for batch in range(groups+1):
                first=4*batch
                self.assertEqual(self.prepare(i,q,size,c,up,down,k,first,samples,coeff),1)
                got,raw,reads=execute(code,list(samples),list(coeff))
                expected=[]
                for m in range(first,first+4):
                    newest=m*down//up;p=m*down%up;phases.add(p)
                    for values in (iv,qv):expected.append(sum(values[newest-t]*cv[p*k+t] for t in range(k) if newest>=t))
                self.assertEqual(got,expected)
                self.assertEqual(len(reads),2*k)
                self.assertEqual(raw[20:32],bytes([0xA5]*12));self.assertEqual(raw[52:64],bytes([0xA5]*12))
            self.assertEqual(len(phases),up)
    def test_extremes_preserve_all_40_bits_without_requantization(self):
        for k in (16,32):
            for value in (-512,511):
                for coeff in (-32768,32767):
                    lane=[value,-value-1,0,1,-1,511,-512,42]
                    got,_,_=execute(instructions(self.dis,'s3_fir_qacc_'+str(k)),lane*k,[coeff]*(8*k))
                    self.assertEqual(got,[x*coeff*k for x in lane])
    def test_invalid_gather_leaves_outputs_untouched(self):
        i=(C.c_int16*64)();c=(C.c_int16*32)();a=(C.c_int16*256)(*([123]*256));b=(C.c_int16*256)(*([456]*256))
        for up,down,k,first,size in [(0,1,16,0,64),(2,1,16,0,64),(1,1,17,0,64),(1,1,16,2**32-1,64),(1,1,16,0,3)]:
            self.assertEqual(self.prepare(i,i,size,c,up,down,k,first,a,b),0)
            self.assertEqual(list(a),[123]*256);self.assertEqual(list(b),[456]*256)
    def test_lane_coefficient_mismatch_is_detected(self):
        code=instructions(self.dis,'s3_fir_qacc_16');samples=list(range(8))*16;coeff=list(range(8,16))*16
        good=execute(code,samples,coeff)[0];bad=execute(code,samples,coeff[1:]+coeff[:1])[0]
        self.assertNotEqual(good,bad)
if __name__=='__main__':unittest.main()

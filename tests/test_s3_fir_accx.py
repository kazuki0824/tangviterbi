import hashlib,json,random,unittest
from pathlib import Path
from experiments.s3_fir_accx_model import instructions,execute
ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'reports/s3-preprocess-break-even/accx'
class AccxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dis=(DIR/'accx.dis').read_text()
    def test_audit_matches_source_and_disassembly(self):
        audit=json.loads((DIR/'accx-audit.json').read_text())
        self.assertEqual(audit['source_sha256'],hashlib.sha256((ROOT/'experiments/s3_fir_accx.S').read_bytes()).hexdigest())
        self.assertEqual(audit['disassembly_sha256'],hashlib.sha256((DIR/'accx.dis').read_bytes()).hexdigest())
        self.assertTrue(all(c['passed'] for c in audit['checks']))
    def check(self,k,iv,qv,c,io,qo):
        actual,reads=execute(instructions(self.dis,'s3_fir_accx_'+str(k)),iv,qv,c,io,qo)
        self.assertEqual(actual,(sum(x*y for x,y in zip(iv,c)),sum(x*y for x,y in zip(qv,c))))
        self.assertEqual(len(reads),2*(k//8+1)+k//8)
    def test_all_independent_halfword_alignments(self):
        rng=random.Random(17)
        for k in (16,32):
            for io in range(0,16,2):
                for qo in range(0,16,2):
                    self.check(k,[rng.randrange(-512,512) for _ in range(k)],[rng.randrange(-512,512) for _ in range(k)],[rng.randrange(-32768,32768) for _ in range(k)],io,qo)
    def test_all_fixed_length_phases_and_extremes(self):
        rng=random.Random(23)
        for up,k in [(32,32),(1443,16)]:
            for phase in range(up):
                self.check(k,[rng.randrange(-512,512) for _ in range(k)],[rng.randrange(-512,512) for _ in range(k)],[rng.randrange(-32768,32768) for _ in range(k)],2*(phase%8),2*((phase+3)%8))
            for value in (-512,511):
                for c in (-32768,32767):self.check(k,[value]*k,[-value-1]*k,[c]*k,14,2)
    def test_wrong_alignment_instruction_changes_result(self):
        code=instructions(self.dis,'s3_fir_accx_16')
        bad=[('ee.vld.128.ip' if op=='ee.ld.128.usar.ip' else op,args) for op,args in code]
        args=(list(range(16)),list(range(16,32)),list(range(-8,8)),2,6)
        self.assertNotEqual(execute(code,*args)[0],execute(bad,*args)[0])
if __name__=='__main__':unittest.main()

import hashlib,json,random,unittest
from pathlib import Path
from experiments.s3_fir_accx_model import instructions
from experiments.s3_fir_qacc_model import execute
from experiments.s3_fir_register_schedule import generate,patterns,symbol
ROOT=Path(__file__).resolve().parents[1];DIR=ROOT/'reports/s3-preprocess-break-even/register'
class RegisterTest(unittest.TestCase):
    def test_all_phase_batches_against_scalar(self):
        rng=random.Random(781);dis=(DIR/'register.dis').read_text()
        for up,down,k in [(32,63,32),(1443,2000,16)]:
            counts=patterns(up,down);groups=sum(counts.values());n=(4*groups+3)*down//up+k
            stream=[(rng.randrange(-512,512),rng.randrange(-512,512)) for _ in range(n)]
            coeff=[rng.randrange(-32768,32768) for _ in range(up*k)]
            for batch in range(groups):
                m=4*batch;newest=[(m+j)*down//up for j in range(4)];offset=tuple(v-newest[0] for v in newest)
                first=newest[0]-(k-1);blocks=(16+max(offset)+3)//4
                # Readable aligned prefix includes a full last vector; history before 0 is zero.
                length=(k//16-1)*16+blocks*4
                history=[v for index in range(first,first+length) for v in (stream[index] if index>=0 else (0,0))]
                cs=[coeff[((m+j)*down%up)*k+(k-1-t)] for t in range(k) for j in range(4) for _ in range(2)]
                got,_,reads=execute(instructions(dis,symbol(k,offset)),history,cs)
                expected=[sum((stream[newest[j]-t][part] if newest[j]>=t else 0)*coeff[((m+j)*down%up)*k+t] for t in range(k)) for j in range(4) for part in range(2)]
                self.assertEqual(got,expected);self.assertEqual(len(reads),blocks*(k//16)+k)
    def test_artifact_matches_generator_and_checks(self):
        r=json.loads((DIR/'register-audit.json').read_text())
        self.assertEqual(r['generator_sha256'],hashlib.sha256((ROOT/'experiments/s3_fir_register_schedule.py').read_bytes()).hexdigest())
        text=''.join(generate(k,offset) for k,up,down in [(32,32,63),(16,1443,2000)] for offset in sorted(patterns(up,down)))
        self.assertEqual(text,(DIR/'register.S').read_text())
        self.assertEqual(r['source_sha256'],hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(r['disassembly_sha256'],hashlib.sha256((DIR/'register.dis').read_bytes()).hexdigest())
        self.assertTrue(all(c['passed'] for c in r['checks']))
    def test_padding_is_not_counted_as_executed(self):
        text='0000 <f>:\n 0: f01d retw.n\n 2: f03d nop.n\n\n'
        self.assertEqual(instructions(text,'f'),[('retw.n',[])])
if __name__=='__main__':unittest.main()

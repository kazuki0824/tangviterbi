import random,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from s3_fir_phase_symmetry import phase_rows,symmetric_dot,report

class PhaseSymmetryTest(unittest.TestCase):
    def test_prototype_symmetry_does_not_imply_every_row_symmetric(self):
        p=[1,2,3,4,5,6,7,8,8,7,6,5,4,3,2,1]
        rows=phase_rows(p,4)
        self.assertTrue(all(rows[k]==rows[3-k][::-1] for k in range(4)))
        self.assertFalse(any(r==r[::-1] for r in rows))
        samples=[3,-4,5,-6]
        with self.assertRaises(ValueError):symmetric_dot(rows[0],samples)
        wrong=sum(rows[0][k]*(samples[k]+samples[-1-k]) for k in range(2))
        self.assertNotEqual(wrong,sum(c*x for c,x in zip(rows[0],samples)))

    def test_exact_dot_and_reverse_storage_for_all_target_phases(self):
        rng=random.Random(20261025)
        for up,taps in [(32,32),(1443,16)]:
            for delta in (-1,0,1):
                n=up*taps+delta
                half=[rng.randrange(-32768,32768) for _ in range((n+1)//2)]
                proto=[half[min(k,n-1-k)] for k in range(n)]
                rows=phase_rows(proto,up)
                for p,coeffs in enumerate(rows):
                    q=(n-1-p)%up
                    samples=[rng.randrange(-512,512) for _ in coeffs]
                    expected=sum(c*x for c,x in zip(coeffs,samples))
                    reconstructed=sum(c*x for c,x in zip(rows[q][::-1],samples))
                    with self.subTest(up=up,delta=delta,phase=p):
                        self.assertEqual(expected,reconstructed)
                        if p==q:self.assertEqual(expected,symmetric_dot(coeffs,samples))
                        self.assertLess(abs(expected),2**39)

    def test_phase_budget_and_scope(self):
        r=report();self.assertEqual(len(r['rows']),6)
        self.assertTrue(all(c['passed'] for c in r['checks']))
        for x in r['rows']:
            self.assertEqual(x['separate_unpack_excludes_beating_raw_low_high'],[True,True])
            self.assertFalse(x['all_algorithms_excluded'])
            self.assertFalse(x['receiver_adopted'])
        t=next(x for x in r['rows'] if x['standard']=='T' and x['prototype_length_delta']==-1)
        self.assertEqual(t['self_symmetric_phases'],[15,31])
        self.assertEqual(t['MAC_only_excludes_beating_raw_low_high'],[False,False])
        s=next(x for x in r['rows'] if x['standard']=='S' and x['prototype_length_delta']==0)
        self.assertEqual(s['self_symmetric_phases'],[721])
        self.assertAlmostEqual(s['ideal_MAC_only_Mcycles_s'],115.4)
        self.assertEqual(s['shared_prototype_Q15_coeff_bytes'],23088)

if __name__=='__main__':unittest.main()

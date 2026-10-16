"""Independent reference properties and nonzero numerical FFT checks."""
import random
import unittest
from experiments.research_sdf_oracle import (
    bit_reverse,coeff,decode_word,encode_word,load_quarter,reference_fft
)
class TestOracle(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.q=load_quarter()
    def test_quadrants(self):
        for p,answer in ((0,(65536,0)),(2048,(0,-65536)),
                         (4096,(-65536,0)),(6144,(0,65536))):
            self.assertEqual(coeff(p,self.q),answer)
    def test_dc_and_impulse(self):
        for n in (2048,4096,8192):
            words=[0]*n
            words[0]=encode_word(16384,0)
            expected=reference_fft(words,self.q)
            self.assertEqual(len(expected),n)
            self.assertEqual(len(set(expected)),1)
            self.assertEqual(decode_word(expected[0]),(16384//n,0))
            constant=[encode_word(8192,0)]*n
            got=reference_fft(constant,self.q)
            self.assertEqual(decode_word(got[0]),(8192,0))
            self.assertEqual(set(got[1:]),{0})
    def test_nonzero_all_modes_against_numpy(self):
        try: import numpy as np
        except ImportError: self.skipTest("numpy required")
        rng=random.Random(41)
        for n in (2048,4096,8192):
            samples=[(rng.randrange(-4000,4001),rng.randrange(-4000,4001)) for _ in range(n)]
            got=reference_fft([encode_word(*x) for x in samples],self.q)
            natural=[complex(*decode_word(got[bit_reverse(k,n.bit_length()-1)])) for k in range(n)]
            expected=np.fft.fft(np.array([complex(*x) for x in samples]))/n
            err=np.abs(np.asarray(natural)-expected)
            self.assertLess(float(err.max()),8.0)
if __name__=="__main__": unittest.main()

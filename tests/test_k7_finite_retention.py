"""Conservation, independent puncture counts and overloaded negative control."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from k7_finite_retention import simulate

class FiniteRetentionTest(unittest.TestCase):
    def test_all_rates_preserve_input_and_expected_step_counts(self):
        for rate,(num,den) in enumerate(((1,2),(2,3),(3,4),(5,6),(7,8))):
            with self.subTest(rate=rate):
                r=simulate(mode=1,segments=(1,5,7),gap=64,symbols=1,rate=rate)
                self.assertTrue(r['conditional_trace_pass'])
                for c,n in enumerate((1,5,7)):
                    self.assertEqual(r['consumed_soft'][c],576*n)
                    self.assertEqual(r['served_pairs'][c],576*n*num//den)
    def test_overloaded_service_cannot_reuse_live_bank(self):
        r=simulate(mode=1,gap=1024,symbols=4)
        self.assertEqual(r['overflow']['kind'],'T bank reused before read complete')
        self.assertFalse(r['conditional_trace_pass'])
    def test_short_trace_must_not_override_sustained_rate_failure(self):
        short=simulate(mode=1,gap=192,symbols=4)
        self.assertTrue(short['conditional_trace_pass'])
        self.assertFalse(short['sustained_read_rate_necessary_pass'])
        long=simulate(mode=1,gap=192,symbols=16)
        self.assertFalse(long['conditional_trace_pass'])
        self.assertEqual(long['overflow']['symbol'],10)

if __name__=='__main__': unittest.main()

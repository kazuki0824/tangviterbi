import unittest
from experiments.s3_reclaim_limits import reclaim_limits

class ReclaimLimitsTest(unittest.TestCase):
    def test_all_sample_phases_and_later_switch_boundaries(self):
        for rate in (16,40):
            r=reclaim_limits(rate);cpp=r['cpp'];budget=r['conservative_reclaim_strict_budget_cycles']
            n=r['minimum_sample_advance']
            for phase in range(cpp):
                # Independent discrete sample counter: index(t)=floor((t+phase)/cpp).
                for end_offset in (0,1,16,64,2064):
                    for extra_bank in (0,1,2000,2064):
                        target=n+end_offset+extra_bank
                        first=target*cpp-phase
                        self.assertGreaterEqual(first,budget)
                        self.assertLess((first-1+phase)//cpp,target)
                        self.assertGreaterEqual((first+phase)//cpp,target)
                        self.assertLess((budget-1+phase)//cpp,target)
            self.assertEqual(n*cpp-(cpp-1),budget)

    def test_packing_deadline_is_later_than_earliest_reclaim_budget(self):
        for rate,release,difference in ((16,303270,9),(40,109308,3)):
            r=reclaim_limits(rate)
            self.assertEqual(r['latest_certified_release_offset_cycles'],release)
            self.assertEqual(r['packing_minus_reclaim_strict_cycles'],difference)
            self.assertFalse(r['receiver_adopted'])

if __name__=='__main__':unittest.main()

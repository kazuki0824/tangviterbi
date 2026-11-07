import unittest
from experiments.s3_arena_limits import capacity, CHUNK

class ArenaLimitsTest(unittest.TestCase):
    def test_prefix_requirement_against_incremental_packing(self):
        carry=0;reserved=0;total=0
        for count in [11264,12288,14351,14352,12289]*100:
            pairs,carry=divmod(count+carry,2)
            reserved+=pairs*5;total+=count
            need=capacity(total,0)['minimum_ordered_retired_chunks']
            for retired in {0,max(0,need-1),need}:
                r=capacity(total,retired)
                self.assertEqual(r['reserved_bytes'],reserved)
                self.assertEqual(r['carry_samples'],carry)
                self.assertEqual(r['capacity_condition_met'],reserved-retired*CHUNK<=4*CHUNK)
                self.assertFalse(r['receiver_adopted'])

    def test_max_bank_four_requires_retirement_even_if_RF_banks_free(self):
        self.assertEqual(capacity(3*14352,0)['free_bytes'],23432)
        self.assertEqual(capacity(4*14352,0)['minimum_ordered_retired_chunks'],1)
        self.assertFalse(capacity(4*14352,0)['capacity_condition_met'])
        self.assertEqual(capacity(4*14352,1)['free_bytes'],20320)
        with self.assertRaises(ValueError):capacity(0,1)

if __name__=='__main__':unittest.main()

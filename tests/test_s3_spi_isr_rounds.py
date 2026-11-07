import unittest
from experiments.s3_spi_isr_rounds import report,explore,successors

class ISRRoundsTest(unittest.TestCase):
    def test_all_interleavings_are_acyclic_and_need_at_most_two_rounds(self):
        r=report()
        self.assertEqual(len(r['rows']),16)
        self.assertEqual(r['max_outer_rounds'],2)
        self.assertTrue(all(x['same_core']['max_outer_rounds']==1 for x in r['rows']))
        self.assertTrue(any(x['max_outer_rounds']==2 for x in r['rows']))
        self.assertIsNone(r['atomic_retry_bound'])
        self.assertIsNone(r['elapsed_upper_cycles'])
        self.assertFalse(r['receiver_adopted'])

    def test_enqueue_and_request_are_separate_and_wip_exits(self):
        s=(0,0,1,0,0,0,0)
        enqueue=dict(successors(s))['enqueue']
        self.assertEqual(enqueue[1],0)
        self.assertEqual(enqueue[3:5],(1,1))
        # Found a transaction: even a pending REQ cannot force another round.
        r=explore((6,1,1,0,2,0,1))
        self.assertEqual(r['max_outer_rounds'],1)

if __name__=='__main__':unittest.main()

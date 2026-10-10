"""Check reservation lifetimes against consumption, not wire average only."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from s3_credit_schedule import schedule

class ScheduleTest(unittest.TestCase):
    def test_reservation_and_snapshot_under_fixed_ingress_contract(self):
        # Independent concrete sequence: at period 1 entry the previous poll
        # freed only 2 of 4 pages. Four new pages require a six-page window.
        for window in (2,4):
            r=schedule(window)
            self.assertFalse(r['conditional_ingress_contract_passes'])
            self.assertIsNotNone(r['first_credit_failure'])
        r=schedule(8)
        self.assertTrue(r['conditional_ingress_contract_passes'])
        self.assertEqual(r['first_snapshot_frontiers'],[2,6,10,14])
        self.assertEqual(r['maximum_reserved_unretired_pages'],6)
        self.assertAlmostEqual(r['period_us'],163.84)
        self.assertAlmostEqual(r['remaining_octal_interval_us'],19.915)
        self.assertFalse(r['RS_RPC_scheduled'])
        self.assertFalse(r['new_first_candidate_qualified'])

if __name__=='__main__': unittest.main()

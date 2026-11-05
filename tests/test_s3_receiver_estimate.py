import unittest
from experiments.s3_receiver_estimate import report,capacity

class EstimateTest(unittest.TestCase):
    def test_header_and_payload_units(self):
        # Independent bit-time calculation, payload bytes / elapsed seconds.
        for gap in (0,20,80,160):
            expected=sum(32768/(((32768*8+80)/(lanes*80))+gap) for lanes in (8,4))
            self.assertAlmostEqual(capacity(gap),expected)
        threshold=report()['max_equal_gap_us_for_S_payload']
        self.assertGreater(capacity(threshold-.001),100)
        self.assertLess(capacity(threshold+.001),100)

    def test_core_budget_and_no_adoption(self):
        r=report();s=next(x for x in r['cpu'] if x['standard']=='S' and x['scenario']=='planning')
        self.assertGreater(s['core_percent'][0][0],100)
        self.assertLess(s['hypothetical_balanced_upper_core_percent'],100)
        lo,hi=s['hypothetical_packing_shift_Mcycles_s_open_interval']
        self.assertLess(lo,hi)
        self.assertFalse(r['receiver_adopted'])

    def test_whole_ledger_delta_and_speed_threshold(self):
        f=report()['FPGA']
        self.assertEqual(f['net_delta_budget']['logic_sites_estimate'],264)
        self.assertEqual(f['net_delta_budget']['BSRAM'],0)
        self.assertGreater(f['logic_growth_scenarios'][1]['occupancy_pct'],100)
        self.assertLess(f['partial_Fmax_MHz'],f['minimum_K7_MHz'])
        self.assertFalse(f['whole_PnR_verified'])

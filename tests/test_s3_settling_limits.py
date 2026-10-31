import unittest
from experiments.s3_settling_limits import limits, report

class SettlingLimitsTest(unittest.TestCase):
    def test_rounding_at_first_busy_and_available_boundaries(self):
        for rate,cp,gate in ((16,15,7931),(40,6,5931)):
            base=limits(rate)
            self.assertEqual(base['busy_blackout_upper_budget_cycles'],(gate-1)*cp)
            self.assertEqual(base['residual_deadline_at_busy_blackout_budget_cycles'],12288*cp+cp-(20000%cp))
            self.assertEqual(base['max_accepted_bank_samples'],14352)
            self.assertEqual(base['nominal_slices_per_worker'],6)
            self.assertEqual(base['max_slices_per_worker'],8)
            for field,key in (('busy_blackout_upper_budget_cycles','busy_case_bound_within_budget'),
                              ('available_blackout_upper_budget_cycles','available_prepare_entry_bound_within_budget')):
                edge=base[field]
                self.assertTrue(limits(rate,edge)[key])
                self.assertFalse(limits(rate,edge+1)[key])

    def test_preparation_and_blackout_share_the_same_window(self):
        for rate in (16,40):
            base=limits(rate);cp=base['cpp'];d=base['ordinary_gap_cycles']
            for written in range(0,12288,137):
                # Independent integer inequality: w+ceil((P+D)/cpp)<=14288.
                p=(14288-written)*cp-d
                self.assertTrue(limits(rate,written*cp,p)['prepared_next_observation_bound_within_budget'])
                self.assertFalse(limits(rate,written*cp,p+1)['prepared_next_observation_bound_within_budget'])

    def test_unknown_and_local_pass_never_certify_receiver(self):
        for row in report()['rows']:
            self.assertIsNone(row['busy_case_bound_within_budget'])
            self.assertIsNone(row['prepared_next_observation_bound_within_budget'])
        r=limits(40,0,0)
        self.assertTrue(r['prepared_next_observation_bound_within_budget'])
        self.assertFalse(r['receiver_adopted']);self.assertFalse(r['actual_schedule_verified'])
        self.assertEqual(r['packing_deadline_from_switch_earliest_cycles'],109312)
        for x in (-1,True,1.5):
            with self.assertRaises(ValueError):limits(40,x)

if __name__=='__main__':unittest.main()

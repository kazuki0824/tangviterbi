import unittest
from experiments.s3_raw_schedule_limits import phase_limit, report


class RawScheduleLimitsTest(unittest.TestCase):
    def test_preparation_phase_bound_including_rounding(self):
        for rate in (16, 40):
            for gap in range(0, 2000*(240//rate)+1, 7):
                r = phase_limit(rate, gap)
                cpp = r['cpp']
                at = r['latest_prepare_observation_written']
                extra = r['max_extra_preparation_cycles']
                self.assertEqual(at+(extra+gap+cpp-1)//cpp, r['switch_limit_written'])
                self.assertGreater(at+(extra+1+gap+cpp-1)//cpp, r['switch_limit_written'])

    def test_current_native_constants_and_utilization_limits(self):
        rows = {r['standard']: r for r in report()['rows']}
        self.assertEqual(rows['S']['unavailable_stop_written'], 5931)
        self.assertEqual(rows['T']['unavailable_stop_written'], 7931)
        self.assertEqual(rows['S']['max_extra_preparation_cycles'], 26148)
        self.assertEqual(rows['T']['max_extra_preparation_cycles'], 35370)
        self.assertAlmostEqual(rows['S']['nominal_bank_period_us'], 307.2)
        for r in rows.values():
            for case in r['nominal_worker_limits']:
                n = case['slices_per_worker_bank']
                self.assertAlmostEqual(case['core0_full_slice_average_ceiling_us']*n+
                                       r['nominal_core0_reference_nonpacking_us'],
                                       r['nominal_bank_period_us'])
                self.assertAlmostEqual(case['core1_full_slice_average_ceiling_us']*n,
                                       r['nominal_bank_period_us'])

    def test_unknown_costs_never_become_a_pass(self):
        r = report()
        self.assertFalse(r['WCET_proven'])
        self.assertFalse(r['actual_schedule_verified'])
        self.assertFalse(r['receiver_adopted'])
        for args in ((17,), (40, -1), (40, 12001)):
            with self.assertRaises(ValueError):
                phase_limit(*args)


if __name__ == '__main__':
    unittest.main()

import unittest
from ci.s3_native_prepare_audit import budget
class NativePrepareBudget(unittest.TestCase):
    def test_nominal_rate_and_per_bank_work_agree(self):
        for rate in (16,40):
            b=budget(rate)
            self.assertEqual(b['body_instructions'],35840)
            self.assertAlmostEqual(b['nominal_fill_instructions_per_s'],rate*1e6*35/12)
    def test_phase_boundary_not_uniform_poll_failure(self):
        for rate in (16,40):
            b=budget(rate);cpp=240//rate;latest=b['latest_entry_written_body_only']
            self.assertLessEqual(latest*cpp+b['ideal_body_cycles'],14288*cpp)
            self.assertGreater((latest+1)*cpp+b['ideal_body_cycles'],14288*cpp)
            self.assertTrue(b['body_exceeds_uniform_poll_budget'])
            self.assertLess(b['samples_during_body_rounded_up'],12288)
    def test_stall_sensitivity_only_tightens_entry(self):
        for rate in (16,40):
            self.assertLess(budget(rate,6)['latest_entry_written_body_only'],budget(rate,5)['latest_entry_written_body_only'])
if __name__=='__main__':unittest.main()

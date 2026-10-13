import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sct", ROOT / "experiments/s3_sct_schedule.py")
sct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sct)


class SCTScheduleTest(unittest.TestCase):
    def test_conditional_phase_sweep_and_two_port_ownership(self):
        result = sct.report()
        self.assertEqual(result["T_phase_sweep"]["failed_phase_count"], 0)
        self.assertTrue(result["S"]["conditional_pass"])
        self.assertLessEqual(result["S"]["maximum_out_of_order_completed_bytes"], 8192)
        self.assertFalse(result["T_without_admission"]["conditional_pass"])
        self.assertGreater(result["T_without_admission"]["deadline_misses"], 0)
        for key in ("T_slow_API", "T_slow_SCT", "S_slow_API"):
            self.assertFalse(result[key]["conditional_pass"])
            self.assertGreater(result[key]["peak_RF_page_reservation"], 32768)
        self.assertLess(sum(result["ordinary_IRQ_capacity_MBps"].values()), 100)


if __name__ == "__main__":
    unittest.main()

"""Regression guards for resource gate: partial-only evidence never passes stage 2."""
import unittest
from ci.fpga_estimate_stage2 import audit

class StageTwoGate(unittest.TestCase):
    def test_stage_two_remains_closed_without_measured_full_receiver(self):
        r=audit()
        self.assertEqual(r["stage"],2)
        self.assertFalse(r["completion"])
        self.assertFalse(r["stage3_permitted"])
        self.assertEqual(r["all_conditions_checked"],len(r["checks"]))
        self.assertEqual(r["ng"],sum(not x["ok"] for x in r["checks"]))
        failures={x["name"] for x in r["checks"] if not x["ok"]}
        self.assertIn("full receiver legal placement",failures)
        self.assertIn("evidence file sha256:routed_netlist",failures)
        self.assertIn("area:t_fir_resample",failures)
        self.assertIn("area:s_ts",failures)

if __name__=="__main__":
    unittest.main()

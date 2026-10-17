"""Unittest invariants for hypothesis-only FFT resource arithmetic."""
import unittest
from experiments.fft_architecture_screen import mode_screen,report
class ScreenTests(unittest.TestCase):
    def test_stage_storage(self):
        for mode in (1,2,3):
            x=mode_screen(mode)
            self.assertEqual(x["hybrid_internal_bytes"]+x["hybrid_external_bytes"],x["all_sdf_delay_bytes"])
    def test_mode3(self):
        x=mode_screen(3)
        self.assertEqual(x["all_sdf_bsram_min"],16)
        self.assertEqual(x["hybrid_bsram_min"],8)
        self.assertEqual(x["hold_bytes"],29952)
        self.assertAlmostEqual(x["external_stage_MBps"],63.0456950457)
        self.assertAlmostEqual(x["hold_spill_MBps"],57.6277056277)
    def test_qualification_unknown(self):
        x=report()
        self.assertFalse(x["receiver_adopted"])
        self.assertIsNone(x["full_sta"])
        self.assertTrue(all(not v["qualified"] for v in x["candidates"]))
        self.assertEqual([v["bsram_budget"] for v in x["candidates"]],[44,52,44,29])
if __name__=="__main__":
    unittest.main()

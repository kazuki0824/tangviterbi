import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
from s3_stream_schedule import simulate


class StreamScheduleTest(unittest.TestCase):
    def test_nominal_ownership_and_queue(self):
        for phase in (0, 1, 26.825, 53.65, 102.3, 519.75):
            with self.subTest(phase=phase):
                result = simulate(phase_us=phase)
                self.assertEqual(result["symbols"], 256)
                self.assertEqual(result["transactions"]["FFT"], 9 * 256)
                self.assertTrue(result["conditional_schedule_pass"])
                self.assertLessEqual(result["maximum_slot_release_us"], 985.75 + 1e-6)

    def test_long_fft_breaks_the_same_buffer_contract(self):
        self.assertGreater(simulate(fft_us=600)["deadline_misses"], 0)

    def test_large_gaps_cannot_be_hidden_in_average_capacity(self):
        self.assertFalse(simulate(gap_us=10)["conditional_schedule_pass"])


if __name__ == "__main__":
    unittest.main()

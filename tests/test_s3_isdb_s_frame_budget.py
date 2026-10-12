"""Frame conservation and growing-versus-bounded RS backlog, not RTL timing."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from s3_isdb_s_frame_budget import report,scenario
class FrameBudgetTest(unittest.TestCase):
 def test_frame_conservation_and_overhead(self):
  r=report();self.assertEqual(48*203*8//2,r['main_symbols'])
  self.assertEqual(192*(203+4)+192,r['frame_symbols'])
  self.assertEqual(r['frame_interleaver_payload_bytes'],77952)
  self.assertAlmostEqual(r['TS_payload_Mbps'],52.17,places=9)
  self.assertLess(r['minimum_clock_MHz']['main_mean'],r['minimum_clock_MHz']['with_burst_zero_queue'])
 def test_mean_capacity_does_not_mean_zero_queue(self):
  low=scenario(90,frames=1024);short=scenario(90,frames=128);mid=scenario(92.6);high=scenario(93.15)
  self.assertFalse(low['steady_main_RS_capacity_pass']);self.assertGreater(low['main_only_max_waiting_codewords'],short['main_only_max_waiting_codewords'])
  self.assertTrue(mid['steady_main_RS_capacity_pass']);self.assertGreater(mid['main_only_max_waiting_codewords'],0)
  self.assertEqual(high['main_only_max_waiting_codewords'],0)
  self.assertFalse(high['deinterleaver_and_TMCC_scheduling_verified'])
if __name__=='__main__':unittest.main()

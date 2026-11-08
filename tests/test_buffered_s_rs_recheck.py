import unittest
from experiments.buffered_s_rs_recheck import run,report,MAIN
class BufferedRSTest(unittest.TestCase):
 def test_negative_average_cannot_be_saved_by_fifo(self):
  r=run(90,MAIN[12],periods=12)
  self.assertFalse(r['capacity_pass']);self.assertFalse(r['periodic_tail_repeats'])
  self.assertGreater(r['tail_backlog_ticks'][1],r['tail_backlog_ticks'][0])
 def test_tmcc_contention_is_not_omitted(self):
  r=run(93.1532,MAIN[0],tmcc_first=True)
  self.assertAlmostEqual(r['max_wait_us'],2667/93.1532,places=6)
  self.assertTrue(r['periodic_tail_repeats']);self.assertGreaterEqual(r['max_waiting_jobs'],1)
 def test_phase_sweep_retains_scope_and_negative_control(self):
  r=report();self.assertAlmostEqual(r['mean_required_MHz'],92.75247802734376)
  self.assertFalse(r['receiver_adopted']);self.assertFalse(r['real_deinterleaver_DMA_arrivals_verified'])
  self.assertFalse(r['scenarios'][0]['all_capacity_pass'])
  for s in r['scenarios'][1:]:
   self.assertTrue(s['all_capacity_pass']);self.assertTrue(s['all_periodic_tails_repeat'])
   self.assertEqual(s['phase_cases'],772)
if __name__=='__main__':unittest.main()

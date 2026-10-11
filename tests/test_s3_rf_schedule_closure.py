"""Regression for capture lateness and CPU affinity hidden by aggregate loads."""
import sys
import unittest
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from s3_rf_schedule_closure import capture_blackouts,core_demand,report

class ScheduleClosureTest(unittest.TestCase):
 def test_uninterrupted_two_core_FFT_loses_a_native_bank(self):
  x=capture_blackouts(phase_us=200)
  self.assertFalse(x['conditional_pass'])
  self.assertEqual(x['first_failed_bank'],1)
  self.assertAlmostEqual(x['worst_switch_lateness_us'],203.5)
  # 2000 native samples at 16 MS/s, not a whole 768us bank period.
  self.assertEqual(x['late_limit_us'],125)
 def test_delay_moves_the_following_bank_threshold(self):
  x=capture_blackouts(phase_us=0)
  self.assertEqual(x['first_failed_bank'],2)
  self.assertAlmostEqual(x['worst_switch_lateness_us'],271.5)
 def test_tile_boundaries_are_only_conditional_poll_opportunities(self):
  x=capture_blackouts(phase_us=200,tiles=5,poll_us=1)
  self.assertTrue(x['conditional_pass'])
  self.assertLessEqual(x['worst_switch_lateness_us'],100)
  self.assertEqual(x['FFT_elapsed_with_poll_gaps_us'],504)
 def test_core_affinity_matters_even_below_aggregate_capacity(self):
  bad=core_demand('T',4,api_core=0)
  good=core_demand('T',4,api_core=1)
  self.assertAlmostEqual(bad['total_utilization'],good['total_utilization'])
  self.assertLess(bad['total_utilization'],1)
  self.assertGreater(bad['core_utilization'][0],1)
  self.assertFalse(bad['selected_budget_pass']);self.assertTrue(good['selected_budget_pass'])
  # Independent arithmetic without the communication model helper.
  api_calls=Fraction(9000000,10395)*10+Fraction(40000000,12288)
  self.assertAlmostEqual(bad['core_utilization'][0]-good['core_utilization'][0],float(api_calls)*20e-6)
 def test_satellite_serial_owner_needs_a_faster_packer(self):
  bad=core_demand('S',6,api_core=1,prepare_core=1)
  self.assertEqual(bad['core_utilization'][0],1)
  self.assertFalse(bad['selected_budget_pass'])
  good=core_demand('S',4,api_core=1,rs_cycles=2000)
  self.assertTrue(good['selected_budget_pass'])
  self.assertFalse(good['CPU_WCET_verified']);self.assertFalse(good['receiver_adopted'])
 def test_entire_phase_grid_and_profiles_are_recorded(self):
  x=report();self.assertEqual(x['summary']['blackout_passes']['1'],0)
  self.assertEqual(len(x['blackouts']),1024)
  self.assertEqual(x['summary']['blackout_passes']['5'],256)
  self.assertEqual(len(x['per_core_demand']),144)
  self.assertFalse(x['complete_estimate'])

if __name__=='__main__':unittest.main()

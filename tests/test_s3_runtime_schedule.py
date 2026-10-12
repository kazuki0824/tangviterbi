from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from s3_runtime_schedule import report,terrestrial
class RuntimeScheduleTest(unittest.TestCase):
 def test_every_mode_GI_and_implemented_affinity(self):
  r=report();self.assertEqual(len(r['cases']),36)
  self.assertEqual({x['points'] for x in r['cases']},{2048,4096,8192})
  self.assertEqual({x['GI'] for x in r['cases']},{1/4,1/8,1/16,1/32})
  self.assertTrue(all(not x['joint_schedule_verified'] and not x['measured_WCET'] for x in r['cases']))
  for n,p in ((2048,259.875),(4096,519.75),(8192,1039.5)):
   x=terrestrial(n,1/32,0);self.assertEqual(x['period_us'],p)
   self.assertEqual(x['slot_deadline_us'],2*p)
   self.assertGreater(x['core0_components']['prepare'],0)
   self.assertEqual(set(x['core1_components']),{'FFT'})
 def test_fixed_route_failure_is_not_hidden_by_CPU_migration(self):
  for n in (2048,4096):
   x=terrestrial(n,1/32,0,pack_cycles=0,api_active_us=0,prepare_cycles=0)
   self.assertLess(x['fixed_route_spare_percent']['Octal'],0)
   self.assertFalse(x['necessary_scenario_pass'])
  x=terrestrial(8192,1/32,500)
  self.assertGreater(x['core_utilization'][0],1)
  self.assertFalse(x['necessary_scenario_pass'])
 def test_extra_work_cannot_improve_deadlines_or_capacity(self):
  a=terrestrial(8192,1/8,400,api_active_us=2)
  b=terrestrial(8192,1/8,450,api_active_us=20,reorder_cycles=10000)
  self.assertGreater(b['core_utilization'][0],a['core_utilization'][0])
  self.assertLess(b['optimistic_same_frame_slack_us'],a['optimistic_same_frame_slack_us'])
  self.assertEqual(report()['runtime32']['S_zero_consumer_service_time_us_upper'],122.88)
if __name__=='__main__':unittest.main()

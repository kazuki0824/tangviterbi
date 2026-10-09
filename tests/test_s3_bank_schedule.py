import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from s3_bank_schedule import simulate, report
class BankScheduleTest(unittest.TestCase):
    def test_policy_catches_bank_reuse_not_just_average_bandwidth(self):
        short=simulate('T',4,ring_bytes=32768)
        large=simulate('T',4,ring_bytes=65536)
        slow=simulate('T',8,ring_bytes=65536)
        self.assertEqual(short['failure'],'raw_bank_prep_deadline')
        self.assertTrue(large['optimistic_event_pass'])
        self.assertLessEqual(large['maximum_ring_reserved_bytes'],65536)
        self.assertLessEqual(large['maximum_slot_release_us'],2079)
        self.assertFalse(large['CPU_IRQ_WCET_verified'])
        self.assertEqual(slow['failure'],'raw_bank_prep_deadline')
    def test_single_owner_satellite_lower_bound(self):
        x=simulate('S',6)
        self.assertTrue(x['optimistic_event_pass'])
        self.assertEqual(x['packing_core_utilization_lower_bound'],1)
        self.assertFalse(x['receiver_adopted'])
        self.assertEqual(simulate('S',8)['failure'],'raw_bank_prep_deadline')
    def test_report_grid(self):
        x=report();self.assertEqual(len(x['runs']),45)
        d=ROOT/'build/s3-capture';d.mkdir(parents=True,exist_ok=True)
        (d/'bank-schedule.json').write_text(json.dumps(x,indent=2)+'\n')

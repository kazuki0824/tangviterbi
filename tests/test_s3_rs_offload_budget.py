"""Reject full-codeword RPC and expose overload in the split's RF ring."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from s3_rs_offload_budget import report
class BudgetTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.result=report()
 def test_full_RS_fails_before_adoption(self):
  r=self.result['profiles']['CPU_all_RS']
  self.assertTrue(all(not a['necessary_bandwidth_pass'] for a in r['communication_assignments']))
  self.assertFalse(r['adopted'])
 def test_every_existing_port_assignment_is_screened(self):
  for name,count in [('CPU_BM_Chien_Forney',4),('CPU_BM_Omega',4),('CPU_BM_Omega_Forney',16)]:
   r=self.result['profiles'][name]
   self.assertEqual(len(r['communication_assignments']),count)
   for a in r['communication_assignments']:
    self.assertTrue(a['necessary_bandwidth_pass'])
    self.assertTrue(a['event_model']['conditional_contract_pass'])
    self.assertLessEqual(a['event_model']['peak_RF_reserved_bytes'],65536)
   self.assertIsNone(r['CPU_performance_pass']);self.assertFalse(r['adopted'])
 def test_larger_API_gap_is_not_hidden_by_RPC_deadline(self):
  r=self.result['negative_control_40us_API']
  self.assertFalse(r['conditional_contract_pass']);self.assertGreater(r['peak_RF_reserved_bytes'],65536)
if __name__=='__main__':unittest.main()

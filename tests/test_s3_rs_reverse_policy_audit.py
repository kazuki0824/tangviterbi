import unittest
from experiments.s3_rs_reverse_policy_audit import calculate,RS_CW_PER_S
class ReversePolicyAudit(unittest.TestCase):
 def setUp(self): self.r=calculate();self.c={x["name"]:x for x in self.r["cases"]}
 def test_all_five(self): self.assertEqual(len(self.c),5)
 def test_rates(self):
  self.assertAlmostEqual(float(RS_CW_PER_S),35541.87192118227)
  self.assertAlmostEqual(self.r["clock_and_rate"]["S1_old_scalar_RS_only_Mcycles_s"],783.052494,places=2)
 def test_transport_is_conditional_not_blanket_failure(self):
  for n in ["S-2/SoC_BM_Chien_Forney","S-3/SoC_BM_Omega","S-4/SoC_BM_Omega_Forney"]:
   self.assertTrue(self.c[n]["aggregate_wire_necessary_condition"])
   self.assertFalse(self.c[n]["only_control_on_FPGA_to_S3"])
   self.assertIsNone(self.c[n]["physical_link_pass"])
  self.assertFalse(self.c["S-1/SoC_all_RS"]["aggregate_wire_necessary_condition"])
 def test_cpu_and_fpga_blockers_are_distinct(self):
  s3=self.c["S-3/SoC_BM_Omega"]
  self.assertGreater(s3["selected_partial_FPGA_logic_lower_bound"],8640)
  self.assertGreater(s3["historical_CPU_low_remaining_cycles_per_CW"][0],0)
  self.assertLess(s3["CPU_high_remaining_if_same_API_model_cycles_per_CW"][1],0)
  self.assertGreater(self.c["S-2/SoC_BM_Chien_Forney"]["selected_scalar_Chien_cycles_per_CW"],self.r["clock_and_rate"]["S3_low_model_remaining_cycles_per_CW_before_API"])
 def test_no_false_adoption(self):
  self.assertTrue(self.r["command_only_design_requirement_retained"])
  self.assertFalse(self.r["reverse_direction_physically_impossible_proven"])
  self.assertFalse(self.r["alternative_receiver_feasible_proven"])
  for x in self.r["cases"]:
   self.assertFalse(x["candidate_adopted"])
   self.assertIsNone(x["CPU_WCET_pass"])
   self.assertIsNone(x["bounded_batch_deadline_pass"])
if __name__=="__main__": unittest.main()

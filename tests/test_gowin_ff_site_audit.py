import unittest
from ci.gowin_ff_site_audit import audit

def cell(kind,**ports):return dict(type=kind,connections={p:[n]for p,n in ports.items()})
class FFResourceTest(unittest.TestCase):
 def test_one_local_output_cannot_feed_two_colocated_ffs(self):
  c={'lut':cell('LUT4',F=10),'a':cell('DFF',D=10),'b':cell('DFFE',D=10)}
  r=audit(c);self.assertEqual(r['minimum_extra_passthrough_LUTs'],1)
  self.assertEqual(r['optimistic_logic_site_lower_bound'],2)
 def test_register_chain_and_hard_block_need_local_luts(self):
  c={'a':cell('DFF',D=1,Q=2),'b':cell('DFF',D=2,Q=3),'ram':cell('DP',DO=1)}
  self.assertEqual(audit(c)['minimum_extra_passthrough_LUTs'],2)
 def test_alu_sum_can_pair_but_carry_cannot(self):
  c={'alu':cell('ALU',SUM=1,COUT=2),'a':cell('DFF',D=1),'b':cell('DFF',D=2)}
  self.assertEqual(audit(c)['minimum_extra_passthrough_LUTs'],1)
 def test_ram_storage_luts_and_other_four_blocked_sites(self):
  c={'ram':cell('RAM16SDP4',DO=1),**{str(i):cell('LUT4')for i in range(4)}}
  self.assertEqual(audit(c)['packed_logic_with_ram_blockers'],8)

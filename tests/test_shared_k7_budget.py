"""Catch the blocker omission that caused the provisional 463-site claim."""
import json,unittest
from pathlib import Path
from experiments.shared_k7_budget import run

class SharedBudgetTest(unittest.TestCase):
 def test_blocked_sites_are_not_free(self):
  r=run();c=next(c for c in r['cases'] if c['trial']=='localshift-162')
  self.assertEqual(c['kernel']['logic_sites_estimate'],6648)
  self.assertEqual(c['kernel']['FF'],2856)
  self.assertEqual(c['kernel_RAM16SDP4'],288)
  self.assertEqual(c['R_H_replacement']['logic_sites_estimate'],21425)
  self.assertEqual(c['remaining']['logic_sites_estimate'],-689)
  self.assertFalse(c['four_resource_allocation_pass'])
 def test_replacement_preserves_other_blocks_and_no_adoption(self):
  r=run();root=Path(__file__).resolve().parents[1]
  old=json.loads((root/'reports/recovery-resource-audit.json').read_text())
  keep={k:sum(v[k]for name,v in old['blocks'].items()if name not in ('T_K7','S_BPSK_QPSK_K7_extra'))for k in r['base_without_both_K7']}
  self.assertEqual(r['base_without_both_K7'],keep)
  for c in r['cases']:
   self.assertEqual(c['R_H_replacement'],{k:keep[k]+c['kernel'][k]for k in keep})
   self.assertFalse(c['adopted']);self.assertIsNone(c['performance_pass'])
  self.assertEqual(r['formally_assigned_routes'],0)

if __name__=='__main__':unittest.main()

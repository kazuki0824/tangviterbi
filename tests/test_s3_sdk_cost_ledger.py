"""Reconciliation checks, not claims about target timing."""
import json,unittest,hashlib
from pathlib import Path
from experiments.s3_joint_runtime import ROOT
from ci.s3_sdk_cost_audit import Binary

class SDKCostLedger(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.ledger=json.loads((ROOT/'reports/s3-sdk-cost-ledger/results.json').read_text())
  cls.runtime=json.loads((ROOT/'reports/s3-sdk-cost-ledger/runtime.json').read_text())
 def test_sources_are_current(self):
  for report in [self.ledger,self.runtime]+self.runtime['profiles']:
   for path,digest in report['source_sha256'].items():
    self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)
 def test_watchdog_delta_excludes_already_charged_predicate(self):
  for p in self.runtime['profiles']:
   self.assertEqual(p['fixed_cost_cycles']['WDT'],272)
  roots=self.ledger['roots']['5']
  self.assertEqual(roots['feed_True']['inclusive_instructions']-roots['feed_False']['inclusive_instructions'],247)
 def test_call_costs_are_closed_and_not_counted_twice(self):
  for roots in self.ledger['roots'].values():
   for path in roots.values():
    self.assertEqual(path['inclusive_instructions'],path['own_instructions']+sum(c['instructions']+c['rom_thunk_instructions'] for c in path['calls']))
    self.assertFalse(any(c['path'].startswith('INDIRECT:') for c in path['calls']))
 def test_running_reap_does_not_call_sdk(self):
  for key in ['raw_running_1','raw_running_2']:
   self.assertEqual(self.ledger['paths'][key]['calls'],[])
 def test_descriptor_loop_cost_matches_loop_visits(self):
  a=self.ledger['paths']['dma_descriptors_5'];b=self.ledger['paths']['dma_descriptors_9']
  self.assertEqual(a['offsets'].count(0x69),5);self.assertEqual(b['offsets'].count(0x69),9)
  self.assertEqual(b['own_instructions']-a['own_instructions'],104)
 def test_rom_hardware_loop_repeats_are_counted(self):
  a=self.ledger['paths']['rom_memcpy20'];b=self.ledger['paths']['rom_memcpy48']
  self.assertEqual(a['offsets'].count(0x18),1);self.assertEqual(b['offsets'].count(0x18),3)
 def test_thunks_bind_public_addresses_to_actual_code(self):
  self.assertEqual(len(self.ledger['verified_rom_thunks']),7)
  for t in self.ledger['verified_rom_thunks'].values():
   self.assertEqual(t['instructions'],2);self.assertNotEqual(t['address'],t['target_address'])
 def test_same_fees_drive_elapsed_and_ledger(self):
  for p in self.runtime['profiles']:
   for r in p['rows']:
    self.assertEqual(r['accounting_identity'],[True,True]);self.assertEqual(r['elapsed_accounting_identity'],[True,True])
    for c in (0,1):
     for k in ['SUBMIT_EMPTY','SUBMIT_DONE','REAP_DONE','WDT']:
      x=r['cost_ledger'][c][k];self.assertEqual(x['cycles'],x['events']*p['fixed_cost_cycles'][k])
 def test_complete_payloads_checked_and_prefix_retained(self):
  for p in self.runtime['profiles']:
   for r in p['rows']:
    self.assertEqual(r['outcome'],0)
    self.assertEqual(r['checked_bytes'],sum(r['transfers_done'])*(32768 if r['rate']==16 else 16384))
    self.assertLessEqual(r['retired_bytes'],r['checked_bytes'])
    if r['accept_reject_reason']==2:self.assertGreater(r['attempted_arena_bytes'],131072)
 def test_unresolved_costs_not_reported_as_zero_or_proven(self):
  self.assertFalse(self.ledger['hardware_wcet']);self.assertFalse(self.runtime['hardware_proven'])
  self.assertTrue(self.runtime['excluded_waits']);self.assertTrue(self.runtime['remaining_allocations'])
 def test_broken_trace_choice_is_rejected(self):
  b=object.__new__(Binary);b.graph=lambda _: {0:dict(op='beqz',args='',edges=[2,4],loop_end=None),2:dict(op='retw',args='',edges=[],loop_end=None),4:dict(op='retw',args='',edges=[],loop_end=None)}
  self.assertRaises(AssertionError,b.trace,'fake',{0:3})
  self.assertEqual(b.trace('fake',{0:4})['own_instructions'],2)
if __name__=='__main__':unittest.main()

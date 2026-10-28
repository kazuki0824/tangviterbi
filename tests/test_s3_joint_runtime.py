"""Independent invariants on the recorded real-C scenario runs.

The source hashes prevent accepting a stale result after changing an operation
or fee. These tests certify the experiment, not ESP32 timing.
"""
import hashlib
import json
import unittest
from pathlib import Path
from experiments.s3_joint_runtime import ROOT, generated

class JointRuntime(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.report=json.loads((ROOT/'reports/s3-joint-runtime/results.json').read_text())
  cls.rows=cls.report['rows']
 def test_sources_and_generated_owner_are_current(self):
  for path,digest in self.report['source_sha256'].items():
   self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)
  for name,source in generated().items():
   self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),self.report['generated_sha256'][name])
 def test_cpu_time_conservation_including_pending_operations(self):
  for row in self.rows:
   self.assertEqual(row['elapsed_accounting_identity'],[True,True])
   self.assertEqual(row['accounting_identity'],[True,True])
   for c in (0,1):
    self.assertEqual(sum(v['cycles'] for v in row['cost_ledger'][c].values())+row['stall_cycles'][c],row['cycles']+row['pending_cycles'][c])
   self.assertEqual(row['pending_cycles'][0],0)
 def test_actual_owner_order_and_shared_fill_budget(self):
  for row in self.rows:
   ledger=row['cost_ledger'][0]
   self.assertEqual(ledger['RF_BASE']['events'],row['polls'])
   self.assertLessEqual(row['polls'],7*row['iterations'][0])
   self.assertLessEqual(ledger['FILL']['events'],row['iterations'][0])
   if row['scenario_pass']:
    self.assertEqual(row['polls'],7*row['iterations'][0])
    self.assertEqual(ledger['COLLECT']['events'],row['iterations'][0])
 def test_transfers_retain_bytes_until_real_prefix_retirement(self):
  for row in self.rows:
   chunk=32768 if row['rate']==16 else 16384
   self.assertEqual(row['checked_bytes'],sum(row['transfers_done'])*chunk)
   self.assertLessEqual(row['retired_bytes'],row['checked_bytes'])
   self.assertLessEqual(row['peak_arena_bytes'],131072)
   self.assertEqual(row['outcome'],0) # Includes byte-for-byte IQ oracle.
 def test_long_run_reaches_watchdog_and_tick_events(self):
  row=next(r for r in self.rows if r['requested_banks']==4000)
  self.assertTrue(row['scenario_pass'])
  self.assertGreater(row['cycles'],600000000)
  for ledger in row['cost_ledger']:
   self.assertGreaterEqual(ledger['WDT']['events'],1)
   self.assertEqual(ledger['TICK_IRQ']['events'],row['cycles']//2400000)
 def test_preparation_failure_is_not_mislabeled_as_arena_overflow(self):
  failures=[r for r in self.rows if r['native_fault']==5]
  self.assertTrue(failures)
  for row in failures:
   self.assertFalse(row['failure_prepared'])
   self.assertLess(row['failure_prepare_done'],7168)
   self.assertGreaterEqual(row['failure_written'],12288)
 def test_negative_control_detects_irq_deadline_failure(self):
  row=next(r for r in self.rows if r['irq_cycles']==30000)
  self.assertFalse(row['scenario_pass'])
  self.assertEqual(row['pack_fault'],6)
 def test_no_hardware_adoption_from_synthetic_costs(self):
  self.assertFalse(self.report['hardware_proven'])
  self.assertFalse(self.report['receiver_adopted'])

if __name__=='__main__':unittest.main()

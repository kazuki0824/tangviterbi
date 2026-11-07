import hashlib
import itertools
import json
import unittest
from experiments.s3_joint_runtime import ROOT
from experiments.s3_owner_order_estimate import owner_variant

class OwnerOrders(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=json.loads((ROOT/'reports/s3-owner-order-estimate/results.json').read_text())
 def test_all_orders_and_preserved_poll_sites(self):
  for order in itertools.permutations('PCAB'):
   s=owner_variant(order)
   self.assertEqual(s.count('poll_rf(r,&prepare_words)'),7)
   self.assertEqual(s.count('unsigned prepare_words='),1)
   self.assertEqual(s.count('pack_slice(r,0)'),1)
   self.assertEqual(s.count('s3_pp_collect('),1)
   self.assertEqual(s.count('s3_pp_spi_reap('),2)
   self.assertEqual(s.count('s3_pp_spi_submit('),2)
  self.assertEqual(len(self.data['profiles']),72)
  for p in self.data['profiles']:
   self.assertEqual(p['generated_sha256']['joint_owner.inc'],hashlib.sha256(owner_variant(p['order']).encode()).hexdigest())
 def test_provenance(self):
  for record in [self.data]+self.data['profiles']:
   for path,digest in record['source_sha256'].items():
    self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)
 def test_same_costs_and_original_order_equivalence(self):
  baseline=json.loads((ROOT/'reports/s3-receiver-cost-ledger/runtime.json').read_text())['profiles']
  for p in self.data['profiles']:
   r=p['rows'][0]
   b=next(b for b in baseline if (b['rows'][0]['rate'],b['rows'][0]['share'])==(r['rate'],r['share']))
   self.assertEqual(p['fixed_cost_cycles'],b['fixed_cost_cycles'])
   if p['order']=='PCAB':
    for r in p['rows']:
     match=next(x for x in b['rows'] if all(x[k]==r[k] for k in ('rate','share','slice_pairs','requested_banks','stall_percent','prepare_per_iteration')))
     self.assertEqual(r,match)
 def test_all_successes_extended_on_s_and_failure_oracles(self):
  for p in self.data['profiles']:
   for r in p['rows']:
    self.assertEqual(r['accounting_identity'],[True,True])
    self.assertEqual(r['elapsed_accounting_identity'],[True,True])
    self.assertEqual(r['outcome'],0)
    self.assertLessEqual(r['peak_arena_bytes'],131072)
    chunk=32768 if r['rate']==16 else 16384
    self.assertEqual(r['checked_bytes'],sum(r['transfers_done'])*chunk)
    if r['accept_reject_reason']==2:self.assertGreater(r['attempted_arena_bytes'],131072)
    if r['scenario_pass']:
     self.assertEqual(r['polls'],7*r['iterations'][0])
     if r['rate']==40 and r['requested_banks']==100:
      self.assertTrue(any(x['requested_banks']==4000 and x['prepare_per_iteration']==r['prepare_per_iteration'] for x in p['rows']))
 def test_no_hardware_claim(self):
  self.assertFalse(self.data['hardware_proven'])
  self.assertFalse(self.data['receiver_adopted'])

if __name__=='__main__':unittest.main()

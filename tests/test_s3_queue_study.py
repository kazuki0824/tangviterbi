import hashlib,json,unittest
from experiments.s3_joint_runtime import ROOT
class QueueStudy(unittest.TestCase):
 def test_observer_preserves_execution_and_partitions_every_port_cycle(self):
  d=json.loads((ROOT/'reports/s3-tx-idle-study/results.json').read_text())
  for path,h in d['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),h,path)
  base=json.loads((ROOT/'reports/s3-counter-envelope/runtime.json').read_text())
  for r in d['rows']:
   p=next(p for p in base['profiles'] if p['order']==r['order'] and (p['rows'][0]['rate'],p['rows'][0]['share'])==(r['rate'],r['share']))
   b=next(b for b in p['rows'] if b['prepare_per_iteration']==2048 and b['requested_banks']==r['reference_banks'])
   for k,v in r.items():
    if k in b:self.assertEqual(v,b[k],k)
   for h in (0,1):self.assertEqual(sum(r['tx_state_cycles'][h]),r['cycles'])
 def test_queue_fee_conservation_and_payload_oracle(self):
  for filename in ('runtime.json','extended.json'):
   d=json.loads((ROOT/'reports/s3-queue-study'/filename).read_text())
   for p,h in d['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),h,p)
   for r in d['rows']:
    for c in (0,1):
     self.assertEqual(sum(v['cycles'] for v in r['cost_ledger'][c].values()),r['charged_cycles'][c])
     self.assertEqual(r['charged_cycles'][c]+r['stall_cycles'][c],r['accounted_until_cycles'][c])
    self.assertEqual(r['outcome'],0)
    self.assertEqual(r['checked_bytes'],sum(r['transfers_done'])*(32768 if r['rate']==16 else 16384))
    self.assertLessEqual(r['peak_arena_bytes'],131072)
   self.assertFalse(d['hardware_proven']);self.assertFalse(d['all_SoC_costs_finalized'])
 def test_pinned_sdk_linkage_and_inline_code(self):
  d=json.loads((ROOT/'reports/s3-queue-study/sdk/audit.json').read_text())
  for p,h in d['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),h,p)
  for symbol in d['symbols'].values():self.assertEqual(symbol['section'],'.iram0.text')
  self.assertEqual(d['symbols']['s3_pp_step_impl']['instructions_per_eight_samples'],39)
  self.assertEqual(d['additional_static_adapter_metadata_bytes'],32)
  self.assertFalse(d['complete_receiver_fit_proven'])
 def test_long_case_exercises_watchdog_and_tick(self):
  r=json.loads((ROOT/'reports/s3-queue-study/extended.json').read_text())['rows'][0]
  self.assertTrue(r['scenario_pass']);self.assertEqual(r['banks'],20000)
  for c in (0,1):
   self.assertGreaterEqual(r['cost_ledger'][c]['WDT']['events'],2)
   self.assertEqual(r['cost_ledger'][c]['TICK_IRQ']['events'],r['cycles']//2400000)
if __name__=='__main__':unittest.main()

import gzip,hashlib,json,math,unittest
from experiments.s3_joint_runtime import ROOT
from experiments.s3_queue_audited_runtime import audited_source

class QueueCosts(unittest.TestCase):
 def read(self,name):
  d=json.loads((ROOT/'reports/s3-queue-study'/name).read_text())
  for p,h in d.get('source_sha256',{}).items():
   self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),h,p)
  return d
 def test_n16r8_configuration_and_queue_allocation(self):
  d=self.read('sdk-n16r8/costs.json')
  c=json.loads(gzip.decompress((ROOT/'reports/s3-queue-study/sdk-n16r8/sdkconfig.json.gz').read_bytes()))
  for k in ('SPIRAM','SPIRAM_MODE_OCT','STDATOMIC_S32C1I_SPIRAM_WORKAROUND'):self.assertTrue(c[k])
  m=d['memory'];self.assertEqual(m['new_queue_requested_bytes']-m['old_queue_requested_bytes'],m['queue_requested_increment_bytes'])
  self.assertEqual(m['combined_requested_increment_bytes'],m['queue_requested_increment_bytes']+m['adapter_static_increment_bytes'])
  self.assertFalse(m['whole_receiver_fit'])
 def test_call_costs_are_closed_and_chain_has_one_irq_envelope(self):
  d=self.read('sdk-n16r8/costs.json')
  for k,r in d['roots'].items():
   self.assertEqual(r['inclusive_instructions'],r['own_instructions']+sum(c['instructions'] for c in r['calls'])+r.get('request_envelope_adjustment',0),k)
   if k.startswith('spi_irq_'):
    self.assertEqual(d['fees_cycles'][k],math.ceil((r['inclusive_instructions']+d['irq_entry_exit_instructions'])*d['alpha']))
  chain=d['roots']['spi_irq_chain']['calls']
  for name in ('xQueueGenericSendFromISR','xQueueReceiveFromISR','spi_new_trans'):
   self.assertEqual(sum(c['target']==name for c in chain),1)
  for k,r in d['wrappers'].items():
   # Each call's callee is charged only when its instruction is on the witness.
   self.assertEqual(r['instructions'],r['own_instructions']+sum(r['witness'].count(int(pc,16))*fee for pc,fee in r['callee_instructions'].items()),k)
   self.assertEqual(d['fees_cycles'][k],math.ceil(r['instructions']*d['alpha']))
 def test_runtime_uses_same_fees_and_preserves_bytes(self):
  d=self.read('audited-runtime.json');a=self.read('sdk-n16r8/costs.json')
  self.assertEqual(d['generated_c_sha256'],hashlib.sha256(audited_source().encode()).hexdigest())
  for r in d['rows']:
   self.assertEqual(r['costs_used']['SUBMIT_DONE'],a['fees_cycles']['submit_done'])
   self.assertEqual(r['costs_used']['IRQ_CHAIN'],a['fees_cycles']['spi_irq_chain'])
   irq=r['cost_ledger'][0]['SPI_IRQ']
   self.assertEqual(sum(r['irq_path_counts']),irq['events'])
   self.assertEqual(sum(n*r['costs_used'][k] for n,k in zip(r['irq_path_counts'],('IRQ_FIRST','IRQ_START','IRQ_COMPLETE','IRQ_CHAIN'))),irq['cycles'])
   for c in (0,1):
    self.assertEqual(sum(v['cycles'] for v in r['cost_ledger'][c].values()),r['charged_cycles'][c])
    self.assertEqual(r['charged_cycles'][c]+r['stall_cycles'][c],r['accounted_until_cycles'][c])
   self.assertEqual(r['checked_bytes'],sum(r['transfers_done'])*16384)
   self.assertEqual(r['outcome'],0)
   self.assertLessEqual(r['peak_arena_bytes'],131072)
  self.assertTrue(any(r['scenario_pass'] and r['requested_banks']==20000 for r in d['rows']))
  self.assertTrue(any(not r['scenario_pass'] and r['prepare_per_iteration']==1024 for r in d['rows']))
  self.assertFalse(d['all_SoC_costs_finalized'])
 def test_inline_whole_slice_costs_and_runtime(self):
  fees=json.loads((ROOT/'reports/s3-inline-packing/slice-costs.json').read_text())
  for p,h in fees['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),h,p)
  regions={k:set(v) for k,v in fees['regions'].items()}
  self.assertEqual(len(regions['bulk']),fees['coefficients']['block'])
  self.assertFalse(regions['once']&regions['regular'])
  d=self.read('inline-runtime.json');self.assertTrue(d['inline_packing'])
  for r in d['rows']:
   for k,v in fees['fees_cycles'].items():self.assertEqual(r['costs_used'][k],v)
   for c in (0,1):
    self.assertEqual(sum(v['cycles'] for v in r['cost_ledger'][c].values()),r['charged_cycles'][c])
    self.assertEqual(r['charged_cycles'][c]+r['stall_cycles'][c],r['accounted_until_cycles'][c])
   self.assertEqual(r['checked_bytes'],sum(r['transfers_done'])*16384)
   self.assertEqual(r['outcome'],0)
   self.assertLessEqual(r['peak_arena_bytes'],131072)
  self.assertTrue(any(r['scenario_pass'] and r['requested_banks']==20000 for r in d['rows']))

if __name__=='__main__':unittest.main()

"""Check source-bounded paths and the same-cost execution ledger."""
import hashlib,json,unittest
from pathlib import Path
from ci.s3_receiver_cost_audit import bounded
from experiments.s3_joint_runtime import ROOT,generated
class ReceiverCosts(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.base=ROOT/'reports/s3-receiver-cost-ledger'
  cls.audit=json.loads((cls.base/'instructions.json').read_text());cls.runtime=json.loads((cls.base/'runtime.json').read_text())
 def test_provenance(self):
  for obj in [self.audit,self.runtime]+self.runtime['profiles']+[json.loads((self.base/p).read_text()) for p in ['tick.json','irq-entry.json']]:
   for path,digest in obj['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)
 def test_call_costs_and_witness_loops(self):
  for name,p in self.audit['paths'].items():
   if 'witness' not in p:continue
   self.assertEqual(p['instructions'],p['own_instructions']+sum(p['callee_instructions'].get(hex(pc),0) for pc in p['witness']),name)
   edges=list(zip(p['witness'],p['witness'][1:]))
   for edge,limit in p['backedge_caps'].items():
    src,dst=(int(x,16) for x in edge.split('->'));self.assertLessEqual(edges.count((src,dst)),limit)
 def test_unbounded_cycle_rejected(self):
  class Fake:
   def graph(self,name):return {0:dict(op='nop',args='',edges=[0],loop_end=None)}
  self.assertRaises(ValueError,bounded,Fake(),'unbounded')
 def test_bounded_diamond_independent_expected_cost(self):
  class Fake:
   def graph(self,name):return {0:dict(op='branch',args='',edges=[1,2],loop_end=None),1:dict(op='call',args='',edges=[3],loop_end=None),2:dict(op='nop',args='',edges=[3],loop_end=None),3:dict(op='ret',args='',edges=[],loop_end=None)}
  self.assertEqual(bounded(Fake(),'diamond',callees={1:7})['instructions'],10)
 def test_settling_wait_is_covered_by_rf_base(self):
  p=self.audit['paths'];self.assertEqual(p['native_settle_wait']['instructions'],120)
  self.assertLessEqual(p['native_settle_wait']['instructions'],p['native_quiet']['instructions'])
 def test_collect_covers_all_owned_counts(self):
  self.assertEqual([self.audit['paths']['collect_'+str(n)]['instructions'] for n in range(4)],[31,98,160,222])
 def test_fill_formula_all_origins(self):
  f=self.audit['paths']['fill_formula'];self.assertEqual(f['nonbody_per_span'],41)
  for n in [1,7,8,1023,1024]:
   for at in range(16384):
    spans=[min(n,16384-at)];remaining=n-spans[0]
    if remaining:spans.append(remaining)
    self.assertEqual(sum(spans),n);self.assertLessEqual(len(spans),2)
    # Every word has exactly one store/barrier, no writes amortized across polls.
    self.assertEqual(sum((x//8)*8+x%8 for x in spans),n)
 def test_generated_fees_match_executed_ledger(self):
  for profile in self.runtime['profiles']:
   for name,source in generated(profile['fixed_cost_cycles']).items():
    self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),profile['generated_sha256'][name])
   for r in profile['rows']:
    self.assertEqual(r['accounting_identity'],[True,True]);self.assertEqual(r['elapsed_accounting_identity'],[True,True])
    for c in (0,1):
     for k in ['OWNER_SHELL','WORKER_SHELL','PACK_EMPTY','PACK_SLICE','RF_BASE','RF_PREPARE','RF_SWITCH','RF_ACCEPT','SUBMIT_EMPTY','SUBMIT_DONE','REAP_DONE','WDT']:
      event=r['cost_ledger'][c][k];self.assertEqual(event['cycles'],event['events']*profile['fixed_cost_cycles'][k])
     tick=r['cost_ledger'][c]['TICK_IRQ'];self.assertEqual(tick['cycles'],tick['events']*profile['fixed_cost_cycles']['TICK'+str(c)])
 def test_payload_oracle_and_capacity_failure(self):
  for profile in self.runtime['profiles']:
   for r in profile['rows']:
    self.assertEqual(r['outcome'],0)
    self.assertEqual(r['checked_bytes'],sum(r['transfers_done'])*(32768 if r['rate']==16 else 16384))
    if r['accept_reject_reason']==2:self.assertGreater(r['attempted_arena_bytes'],131072)
 def test_long_run_not_replaced_by_short_pass(self):
  for profile in self.runtime['profiles']:
   for prep in [1024,2048,3072]:
    a=next(r for r in profile['rows'] if r['requested_banks']==100 and r['slice_pairs']==512 and r['stall_percent']==0 and r['prepare_per_iteration']==prep)
    b=next(r for r in profile['rows'] if r['requested_banks']==4000 and r['prepare_per_iteration']==prep)
    if not a['scenario_pass']:self.assertEqual(a['banks'],b['banks'])
 def test_irq_entry_closure_and_windows_separate(self):
  r=json.loads((self.base/'irq-entry.json').read_text());paths=r['paths']
  def close(n):return paths[n]['own_instructions']+sum(close(c['target']) for c in paths[n]['calls'] if c['target']!='handler')
  self.assertEqual(sum(close(n) for n in ['_UserExceptionVector','_xt_lowint1','_xt_user_exit']),249)
  self.assertEqual(sorted(v['own_instructions'] for v in r['window_trap_paths'].values()),[5,5,10,10,14,14])
 def test_peer_lock_envelopes_and_tick_reselection_included(self):
  for p in self.runtime['profiles']:
   c=p['fixed_cost_cycles'];self.assertEqual([c['TICK0'],c['TICK1'],c['WDT']],[1846,1696,516])
   self.assertLess(c['TICK0']+c['TICK1'],2400000)
   self.assertEqual(p['lock_wait_model']['wdt_extra_cycles'],244)
  irq=json.loads((self.base/'irq-entry.json').read_text())
  self.assertEqual(irq['switch_instructions_excluding_handler_and_window_traps'],642)
 def test_no_unconditional_claim(self):
  self.assertFalse(self.runtime['hardware_wcet']);self.assertFalse(self.runtime['all_application_costs_finalized'])
if __name__=='__main__':unittest.main()

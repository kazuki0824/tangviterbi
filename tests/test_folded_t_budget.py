import gzip,hashlib,json,sys,unittest
from pathlib import Path
from experiments.folded_t_budget import update,ROOT,EVIDENCE,KEYS,CAPS,read
from experiments.folded_t_viterbi import generate
from experiments.s3_viterbi_traceback import generate as baseline
sys.path.insert(0,str(ROOT/'experiments'))
from s3_viterbi_erasure import source as baseline_erasure

class BudgetTest(unittest.TestCase):
 def test_exact_measured_rtl_reproducible(self):
  for p in EVIDENCE.glob('*/summary.json'):
   proof=read(p)
   if proof['baseline']:
    rtl=baseline_erasure().replace('module s3_viterbi_erasure','module folded_t_viterbi') if proof.get('erasures') else baseline('modulo13-pipe').replace('module s3_viterbi_traceback','module folded_t_viterbi')
   else:rtl=generate(proof['lanes'],*(proof.get(k,False) for k in ('pipeline','compact_survivor','onehot','erasures','registered_costs','shift_output')))
   self.assertEqual(rtl,gzip.decompress((p.parent/'dut.sv.gz').read_bytes()).decode(),p.parent.name)
   self.assertEqual(hashlib.sha256(rtl.encode()).hexdigest(),proof['generated_rtl_sha256'])
  self.assertEqual((ROOT/'rtl/folded_t_viterbi.sv').read_text(),generate(16,True,True,True,True,True))
 def test_all_rows_flow_cpu_and_aggregation_preserved(self):
  for board in CAPS:
   original=read(ROOT/f'reports/shared-sdf-evidence/updated-{board}/ownership-variants.json.gz')
   r=update(board)
   self.assertEqual(r,read(EVIDENCE/f'budgets/{board}-all-variants.json.gz'))
   for case in r['cases']:
    self.assertEqual(case['original_count'],448);self.assertEqual(case['allowed_pairs_count'],84)
    byid={row['id']:row for row in case['assignments']}
    for old,new in zip(original,case['assignments']):
     for k in ('id','owners','flows','CPU_before_driver_percent','forward_MBps','reverse_payload_MBps','route_catalog'):
      self.assertEqual(old[k],new[k],(case['trial'],old['id'],k))
     self.assertFalse(new['adopted']);self.assertEqual(new['formal_routes'],[])
    for pair in case['allowed_pairs']:
     t,s=byid[pair['T']],byid[pair['S']]
     expected={k:(max(t['stage_resources'][k],s['stage_resources'][k]) if board=='9k' else t['stage_resources'][k]+s['stage_resources'][k]) for k in KEYS}
     self.assertEqual(pair['stage_resources'],expected)
 def test_completed_T_kernel_does_not_certify_R_H(self):
  r=update('20k');c=next(c for c in r['cases'] if c['trial']=='20k-16-erasure-registered')
  self.assertTrue(c['partial_target_pass']);self.assertTrue(c['erasures'])
  self.assertEqual(c['cycles_per_step'],6)
  self.assertGreater(c['R_H_replacement']['logic_sites_estimate'],CAPS['20k']['logic_sites_estimate'])
  self.assertEqual(c['R_H_replacement']['BSRAM'],45)
  self.assertEqual(r['adopted_receivers'],0)
if __name__=='__main__':unittest.main()

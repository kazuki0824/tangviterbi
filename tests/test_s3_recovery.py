import copy,hashlib,json,subprocess,sys,unittest
from experiments.s3_joint_runtime import ROOT
from ci.s3_recovery_status import validate
class Recovery(unittest.TestCase):
 def test_pending_work_rejects_completion(self):
  p=json.loads((ROOT/'reports/recovery-20261029/plan.json').read_text())
  self.assertFalse(validate(p)['complete'])
  self.assertTrue(validate(p)['ready'])
  bad=copy.deepcopy(p);bad['completion_claim_allowed']=True
  with self.assertRaises(AssertionError):validate(bad)
  r=subprocess.run([sys.executable,'-m','ci.s3_recovery_status','--claim-complete'],cwd=ROOT,capture_output=True,text=True)
  self.assertEqual(r.returncode,2)
 def test_blocking_requires_specific_dependency(self):
  p=json.loads((ROOT/'reports/recovery-20261029/plan.json').read_text());p['items'][0]['status']='blocked'
  with self.assertRaises(AssertionError):validate(p)
 def test_runtime_provenance_accounting_and_byte_oracles(self):
  for name in ('s3-counter-envelope','s3-wait-cost'):
   data=json.loads((ROOT/f'reports/{name}/runtime.json').read_text())
   for record in [data]+data['profiles']:
    for path,digest in record['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)
   for q in data['profiles']:
    for r in q['rows']:
     self.assertEqual(r['accounting_identity'],[True,True]);self.assertEqual(r['elapsed_accounting_identity'],[True,True])
     self.assertEqual(r['outcome'],0)
     self.assertEqual(r['checked_bytes'],sum(r['transfers_done'])*(32768 if r['rate']==16 else 16384))
     self.assertLessEqual(r['peak_arena_bytes'],131072)
     if r['accept_reject_reason']==2:self.assertGreater(r['attempted_arena_bytes'],131072)
   self.assertFalse(data['all_SoC_costs_finalized'])
 def test_wait_coefficients_and_single_charging(self):
  a=json.loads((ROOT/'reports/s3-wait-cost/instructions.json').read_text())
  for path,digest in a['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest)
  for v in a['loops'].values():
   self.assertIsNone(v['iteration_upper_bound'])
   for check in v['checks']:self.assertEqual(check['instructions'],v['base_instructions_already_charged']+sum(a*b for a,b in zip(v['extra_instructions_per_iteration'],check['extra_iterations'])))
  baseline=json.loads((ROOT/'reports/s3-counter-envelope/runtime.json').read_text())
  data=json.loads((ROOT/'reports/s3-wait-cost/runtime.json').read_text())
  for q in data['profiles']:
   r=q['rows'][0];b=next(p for p in baseline['profiles'] if p['order']==q['order'] and (p['rows'][0]['rate'],p['rows'][0]['share'])==(r['rate'],r['share']))
   for k,v in q['fixed_cost_cycles'].items():
    delta=q['extra_cycles']['per_spi_start'] if k in ('IRQ_FIRST','IRQ_START') else q['extra_cycles']['per_tick'] if k in ('TICK0','TICK1') else 0
    self.assertEqual(v,b['fixed_cost_cycles'][k]+delta)
   if not any(q['extra_iterations'].values()):
    for r in q['rows']:self.assertEqual(r,next(x for x in b['rows'] if x['prepare_per_iteration']==2048 and x['requested_banks']==r['requested_banks']))
if __name__=='__main__':unittest.main()

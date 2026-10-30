import hashlib,json,unittest
from ci.s3_queue_allocation_audit import ROOT,OUT,audit
class QueueAllocations(unittest.TestCase):
 def test_saved_target_layout_and_source_accounting(self):
  saved=json.loads((OUT/'allocations.json').read_text())
  self.assertEqual(audit(),saved)
  rows=saved['retained_objects'];self.assertEqual(len({r['type'] for r in rows}),len(rows))
  self.assertEqual(sum(r['retained_bytes'] for r in rows),saved['additional_retained_lower_bound_bytes'])
  self.assertEqual(saved['internal_remaining_upper_bound_bytes']+saved['known_driver_lower_bound_bytes'],saved['previous_internal_remaining_upper_bound_bytes']+saved['previous_known_driver_lower_bound_bytes'])
  self.assertEqual(next(r['retained_count'] for r in rows if r['type']=='gdma_group_t'),1)
  self.assertEqual(saved['transfer_bounce_allocation_calls'],0)
  self.assertFalse(saved['all_SoC_costs_finalized']);self.assertFalse(saved['hardware_boot_executed'])
 def test_lifetime_ledger_reconciles_queue_depth_and_phases(self):
  from ci.s3_queue_lifetime_audit import audit as lifetime
  saved=json.loads((OUT/'lifetime-memory.json').read_text());self.assertEqual(lifetime(),saved)
  self.assertTrue(saved['all_scoped_checks_pass'])
  phases=saved['phases']['fresh_vectors'];self.assertEqual(phases['SPI_live']['requested_bytes'],2352)
  self.assertEqual(phases['PHY_calibration']['requested_bytes']-phases['SPI_live']['requested_bytes'],1904+84)
  self.assertEqual(phases['steady']['requested_bytes']-phases['SPI_live']['requested_bytes'],32+84)
  self.assertEqual(saved['descriptor_count_per_direction'],5)
  self.assertFalse(saved['complete_runtime_heap'])
 def test_periodic_service_accounting_and_baseline(self):
  baseline=next(r for r in json.loads((OUT/'runtime.json').read_text())['rows'] if r['requested_banks']==20000)
  for name,core in [('periodic-runtime.json',0),('timer-core1-runtime.json',1),('periodic-candidates.json',1),('periodic-headroom.json',1)]:
   saved=json.loads((OUT/name).read_text())
   for path,h in saved['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),h,path)
   for r in saved['rows']:
    e=r['cost_ledger'][core]['PHY_TIMER'];self.assertEqual(e['cycles'],e['events']*r['periodic_service_cycles'])
    self.assertEqual(e['events'],max(0,1+(r['cycles']-r['first_release_cycles'])//r['period_cycles']))
    self.assertEqual(r['cost_ledger'][1-core]['PHY_TIMER']['events'],0)
    for c in (0,1):self.assertEqual(sum(v['cycles'] for v in r['cost_ledger'][c].values()),r['charged_cycles'][c])
    if r['periodic_service_cycles']==0:
     for k in ('cycles','banks','peak_arena_bytes','max_rf_poll_gap','checked_bytes'):self.assertEqual(r[k],baseline[k])
   self.assertFalse(saved['all_SoC_costs_finalized'])
 def test_phy_periodic_evidence(self):
  r=json.loads((OUT/'phy-periodic.json').read_text())
  for p,h in r['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),h,p)
  self.assertEqual(r['period_us'],1000000);self.assertEqual(r['dispatch_core'],0)
  self.assertIsNone(r['hardware_wait']['software_iteration_limit'])
  self.assertFalse(r['PLL_tracking_disabled']);self.assertFalse(r['all_SoC_costs_finalized'])
if __name__=='__main__':unittest.main()

import gzip,hashlib,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];DIR=ROOT/'reports/s3-pack-span/cfg'
class CfgTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.result=json.loads((DIR/'results.json').read_text());cls.graphs=json.loads((DIR/'cfg.json').read_text())
 def test_reachable_instruction_boundaries_and_targets(self):
  for name,nodes in self.graphs.items():
   by_pc={int(n['address'],16):n for n in nodes}
   spans=sorted((pc,pc+n['bytes']) for pc,n in by_pc.items())
   for a,b in zip(spans,spans[1:]):self.assertLessEqual(a[1],b[0],name)
   for node in nodes:
    for target in node['edges']:self.assertIn(int(target,16),by_pc,name)
    self.assertFalse(node['op'].startswith('.'),name)
  impl={n['address']:n for n in self.graphs['s3_pp_step_impl']}
  self.assertIn('0x40376caa',impl)
  self.assertNotIn('0x40376ca9',impl) # linear objdump had decoded padding here
  self.assertEqual(impl['0x40376f08']['op'],'retw.n')
 def test_binary_binding_and_partition_certificate(self):
  data=gzip.decompress((ROOT/'reports/s3-pack-span/sdk/n16r8-late-stacks-no-phy-nvs-raw-only-spi/s3_raw_probe.elf.gz').read_bytes())
  self.assertEqual(hashlib.sha256(data).hexdigest(),self.result['ELF_sha256'])
  self.assertTrue(all(c['passed'] for c in self.result['checks']))
  r=self.result['region_nodes'];c=self.result['coefficients']
  self.assertEqual(r['regular']+r['bulk']+r['byte_loop']+r['once'],r['impl'])
  self.assertEqual(c['slice'],r['once']+2*r['candidate_scan']+r['wrapper'])
  self.assertEqual(c['slow_pair'],c['run']+5*r['byte_loop'])
 def test_clock_candidate_retains_unknown_wait_and_epoch(self):
  c=self.result['clock_candidate']
  self.assertFalse(c['wait_retry_upper_bound_known']);self.assertFalse(self.result['cycles_upper_bound_proven'])
  self.assertEqual(c['additional_wait_iteration_instructions'],3)
  self.assertEqual(c['additional_consistency_retry_instructions'],6)
  self.assertNotIn('esp_timer_get_time',self.result['call_bodies_included'])
if __name__=='__main__':unittest.main()

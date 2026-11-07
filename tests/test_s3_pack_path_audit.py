import unittest
from ci.s3_pack_path_audit import run
class PathCountTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.result=run()
 def test_real_c_output_and_conservation_for_all_cases(self):
  self.assertEqual(len(self.result['rows']),24)
  self.assertTrue(all(c['passed'] for c in self.result['checks']))
 def test_reference_full_period_and_slice_frequency(self):
  r=next(r for r in self.result['rows'] if r['bank_samples']==12288 and r['first']==0 and r['slice_pairs']==512)
  self.assertTrue(r['full_output_offset_cycle'])
  for stats in r['stats']:
   self.assertEqual(stats[3],64*6)
   self.assertEqual(4*stats[1]+stats[2],64*3072)
  self.assertEqual(r['rates']['S'][0]['slices_s'],40e6/12288*6)
 def test_smaller_slices_raise_call_counts(self):
  rows=[r for r in self.result['rows'] if r['bank_samples']==12288 and r['first']==0]
  rows.sort(key=lambda r:r['slice_pairs'])
  for a,b in zip(rows,rows[1:]):
   self.assertGreater(a['stats'][0][3],b['stats'][0][3])
if __name__=='__main__':unittest.main()

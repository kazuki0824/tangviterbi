import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from s3_preprocess_break_even import report

class PreprocessBreakEvenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result=report()
        cls.rows={r['id']:r for r in cls.result['rows']}

    def test_terrestrial_fir_net_cost_without_double_packing(self):
        r=self.rows['S3-T-001']
        saving=(40-32.507936507936506)*4800/32768
        self.assertAlmostEqual(r['API_saving_vs_raw_Mcycles_s'],saving)
        self.assertAlmostEqual(r['net_increase_vs_raw_Mcycles_s'][0],430.45436507936506-153.375-saving)

    def test_satellite_fir_expands_representation(self):
        r=self.rows['S3-S-001']
        self.assertAlmostEqual(r['forward_MBps'],115.44)
        self.assertLess(r['API_saving_vs_raw_Mcycles_s'],0)
        self.assertFalse(any(r['beats_raw_same_sensitivity']))

    def test_scope_and_optimistic_zero_transport_comparison(self):
        self.assertEqual(len(self.rows),16)
        self.assertTrue(all(c['passed'] for c in self.result['checks']))
        processed=[r for r in self.rows.values() if r['prefix']]
        self.assertEqual(len(processed),14)
        for r in processed:
            with self.subTest(id=r['id']):
                self.assertFalse(any(r['even_zero_API_beats_raw_same_sensitivity']))
                self.assertFalse(r['receiver_adopted'])
                self.assertEqual(r['formal_routes'],[])
        self.assertIn('SoC TS output',self.rows['S3-S-03f']['endpoint_note'])

if __name__=='__main__':
    unittest.main()

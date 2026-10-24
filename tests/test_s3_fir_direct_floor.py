import sys,unittest
from pathlib import Path
from fractions import Fraction as F
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from s3_fir_direct_floor import direct_mac_cycles,report

class DirectFIRFloorTest(unittest.TestCase):
    def test_exact_work_counts(self):
        self.assertEqual(direct_mac_cycles(F(512,63),32),F(4096,63))
        self.assertEqual(direct_mac_cycles(F(1443,50),16),F(2886,25))

    def test_scoped_exclusion_not_universal(self):
        r=report();self.assertTrue(all(c['passed'] for c in r['checks']))
        t,s=r['rows']
        self.assertEqual(t['MAC_only_excludes_beating_raw'],[True,True])
        self.assertEqual(s['MAC_only_excludes_beating_raw'],[False,True])
        self.assertGreater(s['remaining_for_unpack_loads_reduce_control_Mcycles_s'][0],0)
        for row in (t,s):
            self.assertEqual(row['preserve_old_unpack_excludes_beating_raw'],[True,True])
            self.assertFalse(row['all_same_quality_algorithms_excluded'])
            self.assertFalse(row['receiver_adopted'])

if __name__=='__main__':unittest.main()

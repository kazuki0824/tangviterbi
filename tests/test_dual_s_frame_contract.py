import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from dual_s_frame_contract import scatter_blocks,traffic
from dual_reorder_admission import report

class SFrameContract(unittest.TestCase):
    def test_every_stored_byte_exactly_once(self):
        seen=set()
        for _,frame,columns,blocks in scatter_blocks():
            for col in columns:
                self.assertNotIn((frame,col),seen)
                seen.add((frame,col))
                self.assertIn(col//32,blocks)
        self.assertEqual(seen,{(f,b) for f in range(8) for b in range(204)})
        self.assertEqual(traffic()['write_bursts_per_superframe'],5040)
        self.assertEqual(traffic()['read_bursts_per_superframe'],2688)
        self.assertEqual(traffic()['bytes_per_codeword'],644)

    def test_full_symbol_staging_rejection_is_scoped(self):
        rows=report(12)['input_staging_cases']
        self.assertEqual([x['rejected'] for x in rows],[True,True,False])
        self.assertTrue(all(not x['output_reorder_traffic_included'] for x in rows))
        current=report()['input_staging_cases']
        self.assertEqual([x['rejected'] for x in current],[False,False,False])
        self.assertFalse(report()['full_receiver_adopted'])
        both=report()['input_and_output_staging_cases']
        self.assertEqual([x['rejected'] for x in both],[True,True,True])
        self.assertTrue(all(x['output_reorder_traffic_included'] for x in both))

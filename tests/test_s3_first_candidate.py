"""Independent rate/necessary-condition checks for the fixed candidate."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'experiments'))
from s3_first_candidate import evaluate, rs_service

class FirstCandidateTest(unittest.TestCase):
    def test_continuous_rs_arrivals(self):
        # ONE engine at 90 MHz overflows any finite queue under continuous load.
        arrival = 28_860_000 * 2 / (203 * 8)
        self.assertGreater(arrival, 90_000_000/2667)
        self.assertFalse(rs_service(90)['passes'])
        self.assertTrue(rs_service(99)['passes'])
        self.assertEqual(rs_service(90)['minimum_parallel_engines_for_continuous_rate'], 2)
        self.assertEqual(rs_service(99)['minimum_parallel_engines_for_continuous_rate'], 1)
        self.assertAlmostEqual(rs_service(99)['required_MHz'], 94.7901724137931)

    def test_fixed_route_byte_and_time_conservation(self):
        r = evaluate()
        for st, rf in [('T', 64), ('S', 100)]:
            q = r[st+'_route']
            self.assertAlmostEqual(q['RF_octal_MBps']+q['RF_LCD16_MBps'], rf)
            self.assertTrue(q['feasible_under_contract'])
            # Independently charge command/address, batch and page gaps.
            used_o = q['RF_octal_MBps']/12288*(20+3*(4106/80+.25))
            used_o += q['IQ_octal_up_MBps']/4096*(20+4106/80+.25)
            used_l = (q['RF_LCD16_MBps']+q['LLR_LCD16_MBps'])/4096*(4112/80+8)
            self.assertAlmostEqual(used_o, used_l)
            self.assertLess(used_o, 1)
        self.assertAlmostEqual(r['T_route']['IQ_octal_up_MBps'], 32768/1039.5)
        self.assertAlmostEqual(r['T_route']['LLR_LCD16_MBps'], 4992*6/1039.5)

    def test_partial_fit_cannot_qualify_receiver(self):
        p = dict(variant='s3-memory-fec-compact-b1-rs-acs22-q15-folded-rr',
                 exit_code=0, pnr_trials=[], scope='partial')
        r = evaluate(p)
        for k in ('all_receiver_implemented', 'all_deadlines_verified',
                  'receiver_adopted', 'safe_to_flash'):
            self.assertFalse(r[k])
        self.assertFalse(r['partial_FEC_memory_PnR']['proves_full_receiver'])
        for suffix in ('-shift24', '-rs-offload', '-90MHz'):
            with self.assertRaises(ValueError):
                evaluate(dict(p, variant=p['variant']+suffix))

if __name__ == '__main__':
    unittest.main()

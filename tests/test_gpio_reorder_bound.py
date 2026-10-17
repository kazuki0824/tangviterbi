from fractions import Fraction
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"experiments"))
from gpio_reorder_bound import bound,groups,MIN_N,MAX_N


class GPIOReorderBoundTests(unittest.TestCase):
    def test_all_fragment_geometries(self):
        for n in range(MIN_N,MAX_N+1):
            for a in range(16):
                head=(-a)%16
                tail=(n-head)%16
                bulk=n-head-tail
                self.assertEqual(groups(n,a),bool(head)+bulk//16+bool(tail))
                self.assertGreaterEqual(groups(n,a)*16,n)

    def test_envelope_contains_every_legal_service_and_next_unit(self):
        r=bound(40)
        self.assertEqual(r["count_alignment_cases"],929*16)
        gap=Fraction(MIN_N*240,40)
        for n in range(MIN_N,MAX_N+1):
            for a in range(16):
                end=3000+groups(n,a)*91
                self.assertLessEqual(end,r["max_service_cycles"])
                self.assertLess(end,2*gap)
                # Enumerate every candidate earliest overtaking group until
                # the older unit finishes; later release/overhead only helps.
                count=0
                while gap+count*91<end:
                    count+=1
                self.assertLessEqual(count*40,r["ahead_packed_bytes_bound"])

    def test_unbounded_delay_is_not_claimed_safe(self):
        r=bound(40,extra_start_jitter_cycles=200000)
        self.assertFalse(r["worker_service_bound_pass"])
        self.assertIsNone(r["ahead_packed_bytes_bound"])

    def test_80_msps_cannot_reuse_40_msps_certificate(self):
        r=bound(80)
        self.assertFalse(r["worker_service_bound_pass"])
        self.assertIsNone(r["ahead_packed_bytes_bound"])

    def test_stall_and_jitter_charge_more_storage(self):
        base=bound(40)
        self.assertEqual(base["ahead_packed_bytes_bound"],1600)
        self.assertEqual(base["ahead_expanded_iq32_bytes_bound"],2560)
        jitter=bound(40,extra_start_jitter_cycles=2400)
        pause=bound(40,downstream_pause_cycles=2400)
        self.assertGreater(jitter["ahead_packed_bytes_bound"],1600)
        self.assertEqual(jitter["ahead_packed_bytes_bound"],pause["ahead_packed_bytes_bound"])
        self.assertFalse(base["budget_measured"])
        self.assertFalse(base["receiver_adopted"])


if __name__=="__main__":unittest.main()

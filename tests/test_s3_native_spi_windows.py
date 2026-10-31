import itertools
import unittest
from experiments.s3_native_spi_windows import windows,wire_floor,evaluate

class NativeWindowsTest(unittest.TestCase):
    def test_independent_counter_all_phases_initial_offsets_late_switches(self):
        for rate in (16,40):
            cpp=240//rate
            for phase,e0,deltas in itertools.product(range(cpp),(0,1,1023),itertools.product((0,1,2000),repeat=3)):
                counts=[11264]+[12288+d for d in deltas]
                h=16*cpp+100
                rows=windows(rate,counts,[h]*len(counts))
                end=e0
                for k,row in enumerate(rows):
                    advance=0 if k==0 else end+12288+deltas[k-1]
                    observed=0 if k==0 else advance*cpp-phase
                    accept=observed+16*cpp
                    publish=accept+100
                    self.assertGreaterEqual(accept,row['accept_earliest'])
                    self.assertLessEqual(observed,row['switch_upper'])
                    self.assertLessEqual(publish,row['publish_latest'])
                    if k:end+=counts[k]

    def test_first_bank_not_normal_minimum_and_counts_change_later_windows(self):
        for rate in (16,40):
            cpp=240//rate
            a=windows(rate,[11264,12288,12288]);b=windows(rate,[14352,14352,12288])
            self.assertEqual(a[0]['accept_earliest'],16*cpp)
            self.assertEqual(a[1]['accept_earliest'],(12288-1)*cpp+1+16*cpp)
            self.assertEqual(b[2]['accept_earliest']-a[2]['accept_earliest'],2064*cpp)
            with self.assertRaises(ValueError):windows(rate,[12288,11264])

    def test_wire_floor_is_not_an_upper_bound(self):
        w=wire_floor()
        self.assertEqual([x['wire_floor_cycles'] for x in w],[98334,196668])
        self.assertTrue(all(x['completion_upper_cycles'] is None for x in w))
        self.assertEqual(evaluate(40,[12288]*4)['status'],'unproved')
        self.assertTrue(all(not x['is_lower_bound_from_queue_return'] for x in w))
        r=evaluate(40,[12288]*4,[1000]*4,0,[98334,196668],0)
        self.assertFalse(r['receiver_adopted'])
        self.assertIn('spi_response',r)

if __name__=='__main__':unittest.main()

import unittest
from experiments.t_time_interleaver_layout import LENGTHS,layout,direct_address,audit

class TimeLayoutTest(unittest.TestCase):
    def test_all_modes_lengths_inverse_delay_and_disjoint_storage(self):
        for mode, lengths in LENGTHS.items():
            for length in lengths:
                entries,total=layout(mode,[length]*13)
                end=0
                for seg,carrier,base,depth in entries:
                    self.assertEqual(base,end)
                    self.assertEqual(depth+length*((5*carrier)%96),95*length)
                    e=(seg,carrier,base,depth)
                    if depth:
                        self.assertEqual(direct_address(e,depth),base)
                        self.assertEqual(direct_address(e,depth-1),base+depth-1)
                        self.assertEqual(direct_address(e,3*depth+1),base+(1%depth))
                    else:self.assertIsNone(direct_address(e,123))
                    end+=depth
                self.assertEqual(end,total)
    def test_streaming_tx_rx_inversion_beyond_two_wraps(self):
        # Independent queue delays, unique symbols, all 96 delay classes.
        from collections import deque
        for length in (0,1,2,4,8,16):
            for carrier in range(96):
                tx_depth=length*((carrier*5)%96)
                rx_depth=95*length-tx_depth
                tx=deque([None]*tx_depth);rx=[None]*rx_depth
                for symbol in range(3*95*length+5):
                    tx.append(symbol);wire=tx.popleft()
                    if rx_depth:
                        index=symbol%rx_depth;out=rx[index];rx[index]=wire
                    else:out=wire
                    expected=symbol-95*length
                    self.assertEqual(out,None if expected<0 else expected)
    def test_budget_and_validation(self):
        for mode in LENGTHS:
            r=audit(mode)
            self.assertEqual(r['compact_six_byte_storage'],5690880)
            self.assertEqual(r['rectangular_six_byte_storage'],11381760)
        with self.assertRaises(ValueError):layout(3,[16]*13)

if __name__=='__main__':unittest.main()

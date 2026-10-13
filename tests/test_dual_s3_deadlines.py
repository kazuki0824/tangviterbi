import math
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from dual_s3_deadlines import arrivals, rs_schedule, fft_pass, fft_schedule, SUPERFRAME, T_WORDS, T_PERIOD

class DeadlineTests(unittest.TestCase):
    def test_arrival_conservation_and_burst(self):
        for mode in (1,2,3):
            events=arrivals(8,mode=mode)
            self.assertEqual(sum(s==1 for _,s,_ in events),8*384)
            self.assertEqual(sum(s==2 for _,s,_ in events),8)
            period=T_PERIOD/(2**(3-mode)); words=T_WORDS/(2**(3-mode))
            self.assertEqual(sum(s==0 for _,s,_ in events),math.floor(math.ceil(8*SUPERFRAME/period)*words))
            self.assertEqual([i for _,s,i in events if s==1],list(range(8*384)))
    def test_finite_queues_preserve_all_words(self):
        events=arrivals(4)
        result=rs_schedule(events)
        self.assertEqual(result['codewords'],[sum(s==j for _,s,_ in events) for j in range(3)])
        self.assertLessEqual(result['max_total_waiting_codewords'],20)
        self.assertLessEqual(result['max_latency_us'][1],130)
        self.assertEqual(result['output_credit_wait_us'],0)
    def test_decoder_output_jitter_changes_fifo_peak(self):
        end=rs_schedule(arrivals(4))
        jitter=rs_schedule(arrivals(4),output_timing='alternating')
        self.assertGreater(jitter['max_output_bytes'][1],end['max_output_bytes'][1])
        self.assertEqual(jitter['output_credit_wait_us'],0)
        self.assertEqual(jitter['codewords'],end['codewords'])

    def test_insufficient_fifo_and_unpaced_arrival_are_visible(self):
        short=rs_schedule(arrivals(4),fifo_bytes=(188,188,48))
        long=rs_schedule(arrivals(16),fifo_bytes=(188,188,48))
        self.assertGreater(long['max_input_queue_bytes'],short['max_input_queue_bytes']*3)
        unpaced=rs_schedule(arrivals(4,paced=False))
        self.assertGreaterEqual(unpaced['max_waiting_codewords'][1],384)
        with self.assertRaises(ValueError):rs_schedule(arrivals(1),fifo_bytes=(187,188,48))
    def test_single_buffer_cannot_overlap(self):
        result=fft_pass(8,2,5,3,buffers=1)
        self.assertEqual(result['duration_us'],8*(2+5+3))
    def test_two_buffer_resource_ownership(self):
        result=fft_pass(8,2,5,3)
        self.assertLess(result['duration_us'],80)
        tr=result['trace']
        for tile in range(8):
            ops=[x for x in tr if x['tile']==tile]
            self.assertEqual([x['op'] for x in ops],['read','compute','write'])
            self.assertLessEqual(ops[0]['end_us'],ops[1]['start_us'])
            self.assertLessEqual(ops[1]['end_us'],ops[2]['start_us'])
        for resource in ('bus','compute',0,1):
            ops=[x for x in tr if (x['op']!='compute' if resource=='bus' else
                 x['op']=='compute' if resource=='compute' else x['buffer']==resource)]
            ops.sort(key=lambda x:x['start_us'])
            for a,b in zip(ops,ops[1:]):self.assertLessEqual(a['end_us'],b['start_us'])
    def test_average_bandwidth_pass_is_not_deadline_pass(self):
        self.assertFalse(fft_schedule(2048)['pass_deadline'])
        self.assertFalse(fft_schedule(8192)['pass_deadline'])
        for n in (2048,4096,8192):self.assertTrue(fft_schedule(n,.65)['pass_deadline'])

if __name__=='__main__':unittest.main()

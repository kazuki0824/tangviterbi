import unittest
from collections import deque
from experiments.t_time_block_layout import DelayBlock,allocation,spans,traffic
from experiments.t_time_interleaver_layout import LENGTHS

class BlockTest(unittest.TestCase):
 def test_all_depths_exact_delay_and_wrap(self):
  for length in (0,1,2,4,8,16):
   for delay_class in range(96):
    depth=length*delay_class;dut=DelayBlock(depth);oracle=deque([None]*depth)
    for t in range(0,3*depth+64,16):
     values=[((t+k)<<17)^0x123456789abc for k in range(16)];wanted=[]
     for value in values:oracle.append(value);wanted.append(oracle.popleft())
     self.assertEqual(dut.push(values),wanted,(length,delay_class,t))
 def test_layout_nonalias_and_burst_coverage(self):
  for mode,lengths in LENGTHS.items():
   for length in lengths:
    entries,total,scratch=allocation(mode,[length]*13);end=0
    for _,_,depth,base,size in entries:
     self.assertEqual(base,end);self.assertEqual(base%32,0)
     if depth:
      self.assertGreaterEqual(size,depth+16)
      for batch in (0,1,17,103):
       start=((batch*16-depth)%size)*6
       bursts=spans(base,start,96,size*6)
       self.assertTrue(all(base<=a<base+size*6 and a%32==0 for a in bursts))
       covered={a+b for a in bursts for b in range(32)}
       self.assertTrue({base+(start+k)%(size*6)for k in range(96)}<=covered)
     end+=size*6
    self.assertEqual(end,total)
    self.assertLess(total+2*scratch,8388608)
 def test_mixed_layers(self):
  for mode,lengths in LENGTHS.items():
   result=traffic(mode,[lengths[1]]+[lengths[2]]*5+[lengths[3]]*7)
   self.assertGreater(result['remaining_of_8MiB'],0)
if __name__=='__main__':unittest.main()

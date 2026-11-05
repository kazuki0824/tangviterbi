import unittest
from experiments.s3_arena_limits import capacity
from experiments.s3_native_spi_windows import wire_floor, evaluate
from experiments.s3_spi_prefix_response import connect
from experiments.s3_spi_irq_envelope import worker_event

class TransferSizeTest(unittest.TestCase):
 def test_physical_capacity_and_retired_prefix_are_distinct(self):
  for samples in (12289,57344,65536,100001):
   a=capacity(samples,0,transfer_bytes=16384);b=capacity(samples,0,transfer_bytes=32768)
   self.assertEqual(a['physical_capacity_bytes'],131072)
   self.assertEqual(a['reserved_bytes'],b['reserved_bytes'])
   for chunks in range(a['reserved_bytes']//32768+1):
    self.assertEqual(capacity(samples,2*chunks,transfer_bytes=16384)['occupied_bytes'],capacity(samples,chunks,transfer_bytes=32768)['occupied_bytes'])
  self.assertEqual(capacity(65536,0,transfer_bytes=16384)['minimum_ordered_retired_chunks'],2)
  self.assertEqual(capacity(65536,0,transfer_bytes=32768)['minimum_ordered_retired_chunks'],1)
 def test_wire_irq_period_and_publication_share_transfer_length(self):
  for size,periods in ((16384,[49182,98364]),(32768,[98334,196668])):
   rows=wire_floor(size)
   self.assertEqual([r['wire_floor_cycles'] for r in rows],periods)
   for lanes,L in zip((8,4),periods):
    event=worker_event(lanes,7,transfer_bytes=size)
    for window in (L-1,L,L+1,3*L):
     self.assertEqual((event['burst']+window//event['period'])*event['cost'],(6+2*(window//L))*7)
   banks=[dict(samples=16384,accept_earliest=i*1000,publish_latest=i*1000+100) for i in range(4)]
   r=connect(banks,transfer_bytes=size,scan_bound=1,completion_bounds=[2,3],reap_bound=1)
   self.assertEqual(len(r['ordered_retired_upper_cycles']),163840//size)
   self.assertEqual(r['obligations'][-1]['required'],32768//size)
   e=evaluate(40,[12288]*4,[1000]*4,1,[2,3],1,transfer_bytes=size)
   self.assertEqual(e['spi_response']['transfer_bytes'],size)
   self.assertTrue(all(w['transfer_bytes']==size for w in e['wire']))
 def test_unrecognized_lengths_rejected(self):
  for size in (0,8192,16384.0,True):
   with self.assertRaises(ValueError):capacity(0,0,transfer_bytes=size)
   with self.assertRaises(ValueError):wire_floor(size)
   with self.assertRaises(ValueError):worker_event(8,7,transfer_bytes=size)
if __name__=='__main__':unittest.main()

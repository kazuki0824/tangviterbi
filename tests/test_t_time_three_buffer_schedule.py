import unittest
from experiments.t_time_three_buffer_schedule import requests,roles
from experiments.t_time_block_layout import DelayBlock

class OwnershipTest(unittest.TestCase):
 def test_roles_and_in_place_tile_data(self):
  # Three physical stores, sixteen times, sixteen carriers per tile.
  # Increasing block/time/carrier tags catch overwriting unread input.
  carriers=96
  buffers=[None]*3
  delays=[DelayBlock(4*((i*5)%96)) for i in range(carriers)]
  expected={}
  for block in range(64):
   a,b,c=roles(block);self.assertEqual(len({a,b,c}),3)
   if block>=2:self.assertEqual(buffers[c],expected[block-2])
   buffers[a]=[[100000*block+100*t+i for i in range(carriers)]for t in range(16)]
   if block>=1:
    output=[[None]*carriers for _ in range(16)]
    for first in range(0,carriers,16):
     tile=[row[first:first+16] for row in buffers[b]]
     for j in range(16):
      carrier=first+j
      values=delays[carrier].push([tile[t][j]for t in range(16)])
      for t,value in enumerate(values):
       stamp=(block-1)*16+t-4*((carrier*5)%96)
       oracle=None if stamp<0 else (stamp//16)*100000+(stamp%16)*100+carrier
       self.assertEqual(value,oracle)
       output[t][carrier]=oracle;tile[t][j]=value
     for t in range(16):buffers[b][t][first:first+16]=tile[t]
    expected[block-1]=output
 def test_trace_regions_and_counts(self):
  for batch in (100,101,102):
   streams,meta=requests(batch=batch,competing=True)
   self.assertEqual(meta['requests_per_client'][:3],[14976,14976,63336])
   self.assertGreater(meta['remaining_after_Tspill_Sframe_FFT'],0)
   self.assertEqual(meta['tile_bytes'],1536)
   for stream in streams:
    self.assertTrue(all(address%32==0 for _,_,address,_,_,_ in stream))
if __name__=='__main__':unittest.main()

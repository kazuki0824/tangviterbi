"""Exercise all even byte offsets via I=1, all 96 delay classes, six tiles.
No competing traffic; the one retained input request is in a disjoint region.
"""
import hashlib,json,os
import test_t_time_tile_dma as base

class OffsetTest(base.TileDMATest):
 def test_real_data_and_deadlines(self):
  allocation,fixture,files=base.allocation,base.fixture,base.FILES
  oldenv=dict(os.environ)
  try:
   base.allocation=lambda mode,lengths:allocation(mode,[1]*13)
   def small(*args,**kwargs):
    streams,*other=fixture(*args,**kwargs)
    streams[0]=streams[0][:1];streams[1]=[]
    return (streams,*other)
   base.fixture=small
   base.FILES=[f.replace('experiments/t_time_tile_dma.sv','experiments/t_time_tile_dma_held.sv').replace('experiments/t_time_tile_store.sv','experiments/t_time_tile_store_firstwrite.sv')for f in files]
   os.environ.update(TTI_TILE_COUNT='6',TTI_COMPETING='0',TTI_DMA_REPORT='reports/t-time-tile-dma-held-offsets.json')
   super().test_real_data_and_deadlines()
   p=base.ROOT/os.environ['TTI_DMA_REPORT'];d=json.loads(p.read_text())
   d.update(scope=__doc__,I=1,delay_classes=96,byte_offsets=list(range(0,32,2)))
   d['source_sha256']['tests/test_t_time_tile_dma_held_offsets.py']=hashlib.sha256((base.ROOT/'tests/test_t_time_tile_dma_held_offsets.py').read_bytes()).hexdigest()
   p.write_text(json.dumps(d,indent=2)+'\n')
  finally:
   base.allocation,base.fixture,base.FILES=allocation,fixture,files
   os.environ.clear();os.environ.update(oldenv)

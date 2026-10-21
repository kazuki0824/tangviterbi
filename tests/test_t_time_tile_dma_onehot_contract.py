"""Check exclusive update sources for all 96 delay classes, I=1 (finite RTL run)."""
import hashlib,json,os
import test_t_time_tile_dma_onehot as base

class UpdateContractTest(base.TileDMATest):
 def test_real_data_and_deadlines(self):
  saved=(base.ENGINE,base.allocation,base.fixture,dict(os.environ))
  allocation,fixture=base.allocation,base.fixture
  try:
   base.ENGINE += '''
always @(posedge clk) if(rst && engine.shift_read &&
 (engine.capture_read_0 || engine.capture_read_1 || engine.capture_read_2 || engine.capture_read_3))
 $fatal(1,"read buffer update sources overlap");
'''
   base.allocation=lambda mode,lengths:allocation(mode,[1]*13)
   def small(*args,**kwargs):
    streams,*other=fixture(*args,**kwargs)
    streams[0]=streams[0][:1];streams[1]=[]
    return (streams,*other)
   base.fixture=small
   os.environ.update(TTI_TILE_COUNT='6',TTI_COMPETING='0',TTI_DMA_REPORT='reports/t-time-tile-dma-onehot-contract.json')
   super().test_real_data_and_deadlines()
   p=base.ROOT/os.environ['TTI_DMA_REPORT'];d=json.loads(p.read_text())
   d.update(scope=__doc__,I=1,delay_classes=96,byte_offsets=list(range(0,32,2)),exclusive_update_assertion_passed=True)
   f='tests/test_t_time_tile_dma_onehot_contract.py'
   d['source_sha256'][f]=hashlib.sha256((base.ROOT/f).read_bytes()).hexdigest()
   p.write_text(json.dumps(d,indent=2)+'\n')
  finally:
   base.ENGINE,base.allocation,base.fixture,_=saved
   os.environ.clear();os.environ.update(saved[3])

"""Original finite data/deadline oracle with only the arbiter implementation replaced."""
import test_t_time_tile_dma_onehot as base
class TileDMATest(base.TileDMATest):
 def test_real_data_and_deadlines(self):
  original=base.FILES
  try:
   base.FILES=[f.replace('dual_sdram_refresh_predecode.sv','dual_sdram_bank_parallel.sv') for f in original]
   super().test_real_data_and_deadlines()
  finally:
   base.FILES=original

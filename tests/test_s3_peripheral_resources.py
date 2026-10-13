"""Same-controller clock sharing and physical GDMA pair capacity checks."""
import gzip
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from s3_peripheral_resources import pin_count,gdma_allocation,constraints

class PeripheralResourcesTest(unittest.TestCase):
 def test_clocks_share_only_within_one_I2S_controller(self):
  ps=[dict(name=n,pin_lower_bound=3) for n in ('I2S0_TX40','I2S1_RX40')]
  self.assertEqual(pin_count(ps),6)
  ps.append(dict(name='I2S0_RX40',pin_lower_bound=3))
  self.assertEqual(pin_count(ps),7)
  ps.append(dict(name='I2S1_TX40',pin_lower_bound=3))
  self.assertEqual(pin_count(ps),8);self.assertEqual(pin_count(ps,False),12)
  self.assertTrue(constraints(ps)['I2S_shared_clock_requires_matching_clock_and_slots'])
 def test_SPI_reserves_both_directions_while_LCD_and_I2S_do_not(self):
  ps=[dict(name=n) for n in ('SPI2_Octal80','SPI3_Quad80','LCD8_40','I2S0_TX40','I2S1_TX40','I2S0_RX40')]
  x=gdma_allocation(ps)
  self.assertEqual(x['TX_channels'],5);self.assertEqual(x['RX_channels'],3)
  self.assertTrue(x['selected_driver_capacity_pass'])
  self.assertFalse(gdma_allocation(ps,reserved_pairs=1)['selected_driver_capacity_pass'])
  occupied=[(p['pair'],d) for p in x['allocation'] for d in ('tx','rx') if p[d]]
  self.assertEqual(len(occupied),len(set(occupied)))
 def test_master_40MHz_clock_satisfies_pinned_driver_divider_rule(self):
  x=constraints([])['I2S_40MHz_master_clock']
  self.assertEqual(x['sample_rate_Hz']*x['slots']*x['slot_bits'],x['BCLK_Hz'])
  self.assertEqual(x['sample_rate_Hz']*x['mclk_multiple'],x['MCLK_Hz'])
  self.assertGreater(x['source_Hz'],x['MCLK_Hz']*1.99)
  # A 40MHz slave with the same 160MHz internal source needs div>=8,
  # which requires MCLK320MHz and fails this driver rule.
  self.assertLess(x['source_Hz'],40000000*8*1.99)
 def test_all_saved_assignments_pay_for_the_same_pin_and_DMA_allocation(self):
  data=json.loads(gzip.decompress((ROOT/'reports/s3-partition-audit/estimate.json.gz').read_bytes()))
  profiles={p['name']:p for p in data['profiles']}
  for sub in data['RS_subpartitions'].values():
   for gap in (0,8):
    for row in sub[f'communication_only_gap{gap}']:
     ps=[profiles[n] for n in row['ports']]
     self.assertEqual(row['GPIO_with_control'],pin_count(ps)+3)
     self.assertEqual(row['peripheral_constraints'],constraints(ps))
     self.assertLessEqual(row['peripheral_constraints']['gdma']['pairs_lower_bound'],5)

if __name__=='__main__':unittest.main()

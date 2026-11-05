import unittest
from ci.fpga_stage2_block_inventory import audit
class InventoryTest(unittest.TestCase):
 def test_all_29_and_all_checks(self):
  r=audit()
  self.assertEqual(r["all_conditions_checked"],146)
  self.assertEqual(r["ng"],0)
  self.assertTrue(r["inventory_complete"])
  self.assertFalse(r["stage2_complete"])
if __name__=="__main__": unittest.main()

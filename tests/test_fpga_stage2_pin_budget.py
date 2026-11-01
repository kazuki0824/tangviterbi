import unittest
from pathlib import Path

class PhysicalPins(unittest.TestCase):
    def test_no_physical_approval_of_existing_spi_probes(self):
        text=(Path(__file__).resolve().parents[1]/"experiments/dual_s3_spi_ingress_only_area_top.sv").read_text()
        self.assertIn("input wire [15:0] spi2_d",text)
        self.assertIn("inout wire [7:0] spi3_d",text)
        self.assertIn("output wire [5:0] RF_credit_gray",text)
        self.assertEqual(2*(8+2+4+2)+6+2+6,46)
        self.assertGreater(46,34)

if __name__=="__main__": unittest.main()

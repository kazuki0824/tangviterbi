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
    def test_candidate_necessary_pin_count(self):
        top=(Path(__file__).resolve().parents[1]/"rtl/dual_s3_26pin_transport_candidate.sv").read_text()
        self.assertIn("s3_spi_t_octal_control_endpoint t",top)
        self.assertIn("s3_spi_runtime_endpoint #(.IMAGE_ID(1)",top)
        self.assertNotIn("output wire [5:0] RF_credit_gray",top)
        self.assertEqual(10+16+6+2,34)

if __name__=="__main__": unittest.main()

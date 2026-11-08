import unittest
from ci.stage2_net_provenance import label_from_named_outputs
class NetProvenance(unittest.TestCase):
 def test_only_unique_named_output_nets(self):
  nets={"candidate_input_fir.a":{"bits":[4]},"candidate_rs_ts.a":{"bits":[12]},
        "candidate_fft_k7_core.k7.a":{"bits":[12]}}
  cells={"good":{"connections":{"O":[4],"I":[2]},"port_directions":{"O":"output","I":"input"}},
         "ambiguous":{"connections":{"Y":[12]},"port_directions":{"Y":"output"}},
         "input_only":{"connections":{"I":[4],"Y":[44]},"port_directions":{"I":"input","Y":"output"}}}
  def label(s):
   if s.startswith("candidate_input_fir"):return "ingress_fir"
   if s.startswith("candidate_rs_ts"):return "shared_rs_dual_ts"
   if s.startswith("candidate_fft_k7_core.k7"):return "shared_k7"
  actual,_=label_from_named_outputs(cells,nets,label)
  self.assertEqual(actual,{"good":"ingress_fir","ambiguous":None,"input_only":None})
if __name__=="__main__":unittest.main()

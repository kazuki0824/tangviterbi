"""Synthetic only: exhaustive cell ownership and no double-count checks."""
import unittest
from ci.stage2_mapped_cell_owners import audit,owner,diagnose_unclassified,diagnose_port_cone_ownership,source_owner
class Owners(unittest.TestCase):
 def test_exclusive_assignment(self):
  cells={
   "candidate_fft_k7_core.k7.core.a":{"type":"RAM16SDP4"},
   "candidate_fft_k7_core.memory.reader.a":{"type":"DPB"},
   "candidate_fft_k7_core.fft.stage.a":{"type":"LUT4"},
   "candidate_input_fir.somemap.a":{"type":"ALU"},
   "candidate_rs_ts.decoder.a":{"type":"DFF"},
   "top_glue.a":{"type":"MULT18X18"}
  }
  a=audit(cells)
  self.assertTrue(a["all_mapped_cells_attributed_once"])
  self.assertEqual(sum(sum(x.values()) for x in a["owner_resources"].values()),len(cells))
  self.assertEqual(a["owner_resources"]["shared_k7"]["distributed_ram"],1)
  self.assertEqual(a["owner_resources"]["sdram_service"]["bsram"],1)
  self.assertEqual(a["owner_resources"]["shared_rs_dual_ts"]["ff"],1)
  self.assertTrue(a["has_unclassified_cells"])
 def test_unmatched_port_cones_are_diagnostic_not_verified_ownership(self):
  cells={
    "RF_last_OBUF_O":{"type":"OBUF","attributes":{"src":"rtl/dual_s3_ingress_to_fir_candidate.sv:1"}},
    "RF_last_OBUF_O_LUT4":{"type":"LUT4","attributes":{"src":"gowin/cells_map.v:143"}},
    "mystery_logic":{"type":"LUT2","attributes":{"src":"unidentified"}},
    "candidate_input_fir.fir.a":{"type":"DFF"}
  }
  d=diagnose_unclassified(cells,{"RF_last":{"direction":"output","bits":[1]}})
  self.assertEqual(d["unclassified_total"],3)
  self.assertEqual(d["no_matching_port"],1)
  self.assertTrue(any(x["port"]=="RF_last" and x["resource"]=="logic" for x in d["port_cones"]))
  self.assertTrue(audit(cells)["has_unclassified_cells"])
 def test_port_provenance_requires_unique_subassembly(self):
  src="""
module top;
 dual_s3_ingress_to_fir_candidate candidate_input_fir(.clk(clk),.RF_last(RF_last));
 shared_receiver_fft_metadata candidate_fft_k7_core(.clk(clk),.fft_out_valid(fft_out_valid));
 shared_rs2_dual_ts candidate_rs_ts(.clk(clk),.ts_valid(ts_valid));
endmodule
"""
  cells={"RF_last_OBUF_O":{"type":"OBUF"},
         "fft_out_valid_OBUF_O":{"type":"OBUF"},
         "ts_valid_OBUF_O":{"type":"OBUF"},
         "clk_IBUF":{"type":"IBUF"},
         "random":{"type":"LUT4"}}
  ports={x:{} for x in ("clk","RF_last","fft_out_valid","ts_valid")}
  d=diagnose_port_cone_ownership(cells,ports,src)
  self.assertEqual(d["cells_diagnosed"],5)
  self.assertEqual(sum(x["count"] for x in d["unique_subassembly_port_candidates"]),5)
  self.assertTrue(any(x["candidate_owner"]=="ingress_fir" and x["count"]==1 for x in d["unique_subassembly_port_candidates"]))
  self.assertTrue(any(x["candidate_owner"]=="shared_rs_dual_ts" for x in d["unique_subassembly_port_candidates"]))
  self.assertEqual(d["owner_confidence"],"port-name origin only; not a verified full-receiver cell owner")
 def test_direct_rtl_source_backed_owner_and_gowin_unknown(self):
  self.assertEqual(source_owner({"src":"/runner/work/repo/rtl/isdb_complex_fir33.sv:87.2-117.5"}),"ingress_fir")
  self.assertEqual(source_owner({"src":"/runner/work/repo/rtl/isdb_serial_ts_sink.sv:33.2"}),"shared_rs_dual_ts")
  self.assertIsNone(source_owner({"src":"/runner/oss-cad-suite/share/yosys/gowin/cells_map.v:143.23-144.37"}))
  evidence={
   "renamed_ff":{"type":"DFFCE","attributes":{"src":"rtl/isdb_complex_fir33.sv:87.2"}},
   "renamed_lut":{"type":"LUT4","attributes":{"src":"gowin/cells_map.v:143.2"}},
  }
  result=audit(evidence)
  self.assertEqual(result["owner_resources"]["ingress_fir"]["ff"],1)
  self.assertEqual(result["owner_resources"]["top_level_or_unclassified"]["logic"],1)
  self.assertFalse(result["all_cells_have_verified_owner"])
 def test_specific_prefix_precedes_broad_prefix(self):
  self.assertEqual(owner("candidate_fft_k7_core.memory.foo"),"sdram_service")
  self.assertEqual(owner("candidate_fft_k7_core.fft.foo"),"fft")
  self.assertEqual(owner("candidate_fft_k7_core.k7.foo"),"shared_k7")
  self.assertEqual(owner("candidate_fft_k7_core.other.foo"),"shared_core_other")
if __name__=="__main__": unittest.main()

"""Guard the scope and instruction-evidence rejection for T preprocessing."""

import hashlib
import importlib.util
import json
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("capacity", ROOT / "ci/t_fir_capacity_audit.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class CapacityEvidenceTest(unittest.TestCase):
    def test_even_full_scalar_word_stores_exceed_two_cores(self):
        row = audit.capacity_floor(4)
        self.assertEqual(row["preparation_output_bytes_per_batch"], 1024)
        self.assertEqual(row["minimum_store_instructions_per_batch"], 256)
        self.assertAlmostEqual(row["minimum_store_Mcycles_per_second"], 520.1269841269841)
        self.assertTrue(row["exceeds_two_core_capacity"])

    def test_vector_variant_is_not_rejected_by_scalar_argument(self):
        self.assertFalse(audit.capacity_floor(16)["exceeds_two_core_capacity"])

    def test_missing_function_has_no_proof(self):
        self.assertFalse(audit.inspect_disassembly("unrelated text")["scalar_store_proof_supported"])

    def test_vector_store_invalidates_scalar_evidence(self):
        dis = "00000000 <s3_fir_qacc_prepare>:\n 0: 000000 ee.vst.128.ip q0, a2, 16\n 4: 000000 s16i a3, a2, 0\n"
        self.assertFalse(audit.inspect_disassembly(dis)["scalar_store_proof_supported"])

    def test_out_of_line_memory_helper_invalidates_evidence(self):
        dis = ("00000000 <s3_fir_qacc_prepare>:\n 0: 000000 call8 3\n"
               " 0: R_XTENSA_SLOT0_OP memcpy\n 3: 000000 s16i a3, a2, 0\n")
        self.assertFalse(audit.inspect_disassembly(dis)["scalar_store_proof_supported"])

    def test_truncated_saved_disassembly_cannot_regenerate_a_capacity_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            for flag in audit.FLAGS:
                (output / ("prepare-" + flag + ".dis")).write_text(
                    "00000000 <s3_fir_qacc_prepare>:\n 0: 000000 s16i a3, a2, 0\n")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(audit.run(output), 1)
            result = json.loads((output / "qacc-preparation-capacity.json").read_text())
            self.assertEqual(result["status"], "EVIDENCE_CHECK_FAILED")
            self.assertEqual(len(result["variants"]), 3)
            for row in result["variants"]:
                self.assertNotIn("necessary_capacity", row)

    def test_saved_source_and_all_optimization_variants(self):
        directory = ROOT / "reports/s3-t-preprocess-capacity"
        result = json.loads((directory / "qacc-preparation-capacity.json").read_text())
        self.assertFalse(result["target_runtime_executed"])
        self.assertFalse(result["all_T_preprocessing_excluded"])
        self.assertEqual(result["status"], "REJECT_EXISTING_SCALAR_PREPARE")
        for name, expected in result["source_sha256"].items():
            with self.subTest(source=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)
        self.assertEqual([row["optimization"] for row in result["variants"]], list(audit.FLAGS))
        for row in result["variants"]:
            with self.subTest(optimization=row["optimization"]):
                data = (directory / row["disassembly"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), row["disassembly_sha256"])
                observed = audit.inspect_disassembly(data.decode())
                self.assertEqual(observed, row["analysis"])
                self.assertTrue(observed["scalar_store_proof_supported"])
                self.assertEqual(row["necessary_capacity"], audit.capacity_floor(observed["maximum_scalar_store_bytes"]))
        self.assertTrue(all(row["passed"] for row in result["checks"]))


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_pnr_evidence", ROOT / "ci" / "validate_pnr_evidence.py"
)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

ROUTED_FAILURE = (
    "Info: Routing complete.\n"
    "ERROR: Max frequency for clock 'clk': 105.41 MHz (FAIL at 110.00 MHz)\n"
)
FAIL_SUMMARY = (
    "- P&R at 110 MHz: **FAIL**\n"
    "- Placement/routing completed: **yes**\n"
    "- 110 MHz timing criterion: **FAIL**\n"
    "- extracted routed Fmax: **105.41 MHz**\n"
)
ROUTED_SUCCESS = "Info: Routing complete.\n"
PASS_SUMMARY = "- P&R at 110 MHz: **PASS**\n"


class ValidatePnrEvidenceTests(unittest.TestCase):
    def test_known_routed_timing_miss_is_a_measurement_not_timing_pass(self):
        outcome = validator.verify(
            "9k", "mem-32acs-rsconst", 110,
            "failure", ROUTED_FAILURE, FAIL_SUMMARY,
        )
        self.assertIn("MEASURED TIMING MISS", outcome)
        self.assertIn("NOT certified", outcome)

    def test_successful_routing_is_accepted(self):
        self.assertIn("PASS:", validator.verify(
            "20k", "core-only", 110,
            "success", ROUTED_SUCCESS, PASS_SUMMARY,
        ))

    def test_packing_diagnostic_cannot_claim_routed_timing(self):
        self.assertIn("PASS:", validator.verify(
            "9k", "rs-only", 110, "success", "Info: packing completed",
            "- P&R: **not run (diagnostic)**",
        ))

    def test_unexpected_design_failure_is_never_waived(self):
        with self.assertRaisesRegex(ValueError, "unexpected CAD failure"):
            validator.verify(
                "20k", "mem-32acs-rsconst", 110,
                "failure", ROUTED_FAILURE, FAIL_SUMMARY,
            )

    def test_65mhz_feasibility_failure_is_never_waived(self):
        with self.assertRaisesRegex(ValueError, "unexpected CAD failure"):
            validator.verify(
                "9k", "mem-32acs-rsconst", 65,
                "failure", ROUTED_FAILURE, FAIL_SUMMARY,
            )

    def test_placer_error_is_not_a_timing_only_miss(self):
        with self.assertRaisesRegex(ValueError, "did not finish routing"):
            validator.verify(
                "9k", "mem-32acs-rsconst", 110,
                "failure", "ERROR: Unable to find legal placement",
                FAIL_SUMMARY,
            )

    def test_other_error_is_not_silenced(self):
        with self.assertRaisesRegex(ValueError, "exclusively post-route"):
            validator.verify(
                "9k", "mem-32acs-rsconst", 110, "failure",
                ROUTED_FAILURE + "ERROR: unexpected tool fault\n",
                FAIL_SUMMARY,
            )

    def test_out_of_scope_report_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs from measured"):
            validator.verify(
                "9k", "mem-32acs-rsconst", 110,
                "failure", ROUTED_FAILURE,
                FAIL_SUMMARY.replace("105.41", "110.00"),
            )

    def test_missing_artifacts_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            validator.verify(
                "9k", "mem-32acs-rsconst", 110,
                "failure", "", FAIL_SUMMARY,
            )


if __name__ == "__main__":
    unittest.main()

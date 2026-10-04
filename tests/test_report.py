import json
from pathlib import Path
import subprocess
import tempfile
import unittest


class ReportTests(unittest.TestCase):
    def report(self, log, data=None, rc=0, diagnostic=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "pnr.log").write_text(log)
            if data is not None:
                (root / "report.json").write_text(json.dumps(data))
            return subprocess.check_output([
                "python3", "ci/report.py", "--board", "9k", "--variant", "rs-only" if diagnostic else "mem",
                "--report", str(root / "report.json"),
                "--pnr-log", str(root / "pnr.log"),
                "--synth-log", str(root / "synth.log"), "--exit-code", str(rc),
                *(["--pack-only"] if diagnostic else []),
            ], text=True)

    def test_failed_fit_retains_utilization_but_not_target_fmax(self):
        result = self.report(
            "Info: LUT4: 7266/ 8640 84%\nInfo: BSRAM: 3/ 26 11%\n"
            "Info: target frequency 110 MHz\nERROR: Unable to find legal placement\n",
            rc=125,
        )
        self.assertIn("| LUT4 | 7266 | 8640 |", result)
        self.assertIn("| BSRAM | 3 | 26 |", result)
        self.assertIn("before placement", result)
        self.assertIn("**unknown**", result)
        self.assertNotIn("routed Fmax:", result)

    def test_report_uses_slowest_clock_not_largest_achieved_or_constraint(self):
        result = self.report("Info: Routing complete.\n", {"fmax": {
            "clk": {"achieved": 87.5, "constraint": 110},
            "other": {"achieved": 150, "constraint": 110},
        }}, rc=1)
        self.assertIn("**87.50 MHz**", result)
        self.assertIn("timing criterion: **FAIL**", result)

    def test_log_uses_last_routed_result(self):
        result = self.report(
            "Info: Max frequency for clock 'clk': 120 MHz (PASS at 110 MHz)\n"
            "Info: Routing complete.\n"
            "Info: Max frequency for clock 'clk': 95 MHz (FAIL at 110 MHz)\n",
            rc=1,
        )
        self.assertIn("**95.00 MHz**", result)

    def test_pre_route_frequency_is_not_routed_result(self):
        result = self.report(
            "Info: Max frequency for clock 'clk': 120 MHz (PASS at 110 MHz)\n"
            "ERROR: routing failed\n", rc=1,
        )
        self.assertIn("**unknown**", result)

    def test_partial_json_on_routing_failure_has_unknown_fmax(self):
        result = self.report(
            "ERROR: routing failed\n",
            {"fmax": {"clk": {"achieved": 120, "constraint": 110}}}, rc=1,
        )
        self.assertIn("**unknown**", result)
        self.assertNotIn("routed Fmax:", result)

    def test_routing_marker_does_not_promote_pre_route_log_clock(self):
        result = self.report(
            "Info: Max frequency for clock 'clk': 120 MHz (PASS at 110 MHz)\n"
            "Info: Routing complete.\n", rc=1,
        )
        self.assertIn("**unknown**", result)
        self.assertNotIn("routed Fmax:", result)

    def test_diagnostic_does_not_claim_pnr_or_timing_pass(self):
        result = self.report(
            "Info: LUT4: 4420/ 8640 51%\n",
            {"fmax": {"clk": {"achieved": 200}}}, diagnostic=True,
        )
        self.assertIn("Blocks: RS; controller: **none**", result)
        self.assertIn("P&R: **not run (diagnostic)**", result)
        self.assertIn("| LUT4 | 4420 | 8640 |", result)
        self.assertNotIn("routed Fmax:", result)

    def test_resource_counts_use_same_packed_basis_after_routing(self):
        result = self.report(
            "Info: LUT4: 6298/ 8640 72%\nInfo: Routing complete.\n",
            {"utilization": {"LUT4": {"used": 6000, "available": 8640}},
             "fmax": {"clk": {"achieved": 37.04}}}, rc=1,
        )
        self.assertIn("| LUT4 | 6298 | 8640 |", result)
        self.assertIn("before placement", result)
        self.assertIn("**37.04 MHz**", result)


if __name__ == "__main__":
    unittest.main()

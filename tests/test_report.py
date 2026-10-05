import json
from pathlib import Path
import subprocess
import tempfile
import unittest


class ReportTests(unittest.TestCase):
    def report(self, log, data=None, rc=0, diagnostic=False, performance=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "report.py").write_text(Path("ci/report.py").read_text())
            (root / "performance.json").write_text(json.dumps(
                performance or json.loads(Path("ci/performance.json").read_text())))
            (root / "pnr.log").write_text(log)
            if data is not None:
                (root / "report.json").write_text(json.dumps(data))
            return subprocess.check_output([
                "python3", str(root / "report.py"), "--board", "9k", "--variant", "rs-only" if diagnostic else "mem",
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

    def test_clock_pass_does_not_claim_sustained_throughput(self):
        result = self.report(
            "Info: Routing complete.\n",
            {"fmax": {"clk": {"achieved": 120}}},
        )
        self.assertIn("100.88 MHz Viterbi clock criterion: **PASS**", result)
        self.assertIn("110 MHz timing criterion: **PASS**", result)
        self.assertIn("End-to-end sustained throughput: **not measured", result)

    def test_rs_parallelism_changes_floor_without_changing_workload_or_target(self):
        settings = json.loads(Path("ci/performance.json").read_text())
        for syndrome_cycles, bound in ((16, 6766), (8, 5134), (4, 4318), (0, 3502)):
            with self.subTest(syndrome_cycles=syndrome_cycles):
                profile = {**settings, "rs_syndrome_cycles_per_byte": syndrome_cycles}
                result = self.report("Info: Routing complete.\n", {
                    "fmax": {"clk": {"achieved": 102}}}, rc=1, performance=profile)
                rs_minimum = bound * 25220000 / (204 * 8 * 1e6)
                self.assertIn(f"RS service bound: **{bound} clocks/block**", result)
                self.assertIn(f"Minimum RS clock from cycle budget: **{rs_minimum:.2f} MHz**", result)
                self.assertIn(f"Minimum shared clock from cycle budgets: **{max(100.88, rs_minimum):.2f} MHz**", result)
                self.assertIn("100.88 MHz Viterbi clock criterion: **PASS**", result)
                self.assertIn("Hard throughput clock criterion: **" +
                              ("FAIL" if syndrome_cycles == 16 else "PASS") + "**", result)
                self.assertIn("110 MHz timing criterion: **FAIL**", result)

    def test_32acs_constant_rs_exposes_terrestrial_and_satellite_floors(self):
        settings = json.loads(Path("ci/performance.json").read_text())
        profile = {
            **settings,
            "acs_lanes": 32,
            "rs_syndrome_cycles_per_byte": 0,
        }
        result = self.report(
            "Info: Routing complete.\n",
            {"fmax": {"clk": {"achieved": 80}}},
            rc=1,
            performance=profile,
        )
        self.assertIn("50.44 MHz Viterbi clock criterion: **PASS**", result)
        self.assertIn("Minimum RS clock from cycle budget: **54.12 MHz**", result)
        self.assertIn("Minimum shared clock from cycle budgets: **54.12 MHz**", result)
        self.assertIn("ISDB-S Viterbi clock criterion: **57.72 MHz (PASS)**", result)
        self.assertIn("ISDB-S minimum RS clock from cycle budget: **61.93 MHz**", result)
        self.assertIn("ISDB-S minimum shared clock from cycle budgets: **61.93 MHz**", result)
        self.assertIn("ISDB-S hard throughput clock criterion: **PASS**", result)
        self.assertIn("110 MHz timing criterion: **FAIL**", result)


if __name__ == "__main__":
    unittest.main()

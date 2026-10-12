import gzip
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import s3_link_cpu_sensitivity as model


class LinkCpuSensitivityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads(gzip.decompress((ROOT / "reports/s3-partition-audit/estimate.json.gz").read_bytes()))
        cls.result = model.calculate(cls.audit)

    def test_shorter_modes_do_not_inherit_mode3_fixed_route_pass(self):
        for row, n in zip(self.result["T_modes"], (2048, 4096, 8192)):
            period = Fraction(n * 1008 * 33, 8192 * 32)
            self.assertEqual(row["GI_1_32_period_us"], float(period))
            self.assertAlmostEqual(row["FFT_each_direction_MBps"], float(4 * n / period))
        self.assertEqual([r["fixed_octal_average_time_condition_pass"] for r in self.result["T_modes"]], [False, False, True])
        self.assertTrue(all(not r["all_mode_routes_rejected"] for r in self.result["T_modes"]))

    def test_api_replaces_legacy_charge_instead_of_double_counting(self):
        old = next(r for r in self.audit["assignments"] if r["id"] == "S3-T-004")
        boundary = (old["required_down_MBps"] + old["required_up_MBps"]) * 200 / 4096
        calls = Fraction(40000000, 12288) + 9 * Fraction(1000000, 1) / Fraction(2079, 2)
        expected = (old["CPU_low_high_Mcycles_s"][0] - boundary + float(calls) * 4800 / 1e6) / 480 * 100
        self.assertAlmostEqual(self.result["T_A_Mode3_fixed_route_CPU_low_high_percent"][0], expected)
        zero = model.calculate(self.audit, api_active_us=0)
        self.assertAlmostEqual(zero["T_A_Mode3_fixed_route_CPU_low_high_percent"][0],
                               (old["CPU_low_high_Mcycles_s"][0] - boundary) / 480 * 100)
        for bad in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError): model.active_cycles(bad)

    def test_rpc_api_count_depends_on_pages_and_port(self):
        name = "CPU_BM_Omega"
        spec = self.audit["RS_subpartitions"][name]
        batch_s = self.audit["rates"]["RS_batch_us"] / 1e6
        rows = [r for r in self.result["RS_route_API_sensitivity"][name]["gap0"]
                if r["ports"] == ["SPI2_Octal80", "SPI3_Quad80"]]
        self.assertEqual(len(rows), 4)
        for row in rows:
            expected = sum((1 if "Octal" in p else msg["pages"]) / batch_s
                           for p, msg in zip(row["message_ports"], spec["records"]))
            self.assertAlmostEqual(row["RPC_API_invocations_per_s"], expected)
            budget = row["solver_remaining_cycles_per_CW_low_high"]
            self.assertLess(budget[0], 1320)
            self.assertLess(budget[1], 0)

    def test_new_rf_stripe_pays_rpc_time_and_preserves_every_sample(self):
        caps = {p["name"]: p for p in self.audit["profiles"]}
        for scenarios in self.result["RS_route_API_sensitivity"].values():
            for rows in scenarios.values():
                for row in rows:
                    self.assertAlmostEqual(sum(row["RF_MBps_allocation"]), 100)
                    for n, rf, available in zip(row["ports"], row["RF_MBps_allocation"], row["RF_remaining_port_MBps"]):
                        self.assertLessEqual(rf, available + 1e-7)
                        if caps[n]["kind"] == "up": self.assertEqual(rf, 0)

    def test_all_owners_and_unknown_performance_are_retained(self):
        self.assertEqual(len(self.result["ownerships"]), 320)
        self.assertEqual({r["id"] for r in self.result["ownerships"]}, {r["id"] for r in self.audit["assignments"]})
        for row in self.result["ownerships"]:
            self.assertIsNone(row["whole_FPGA_resources"])
            self.assertIsNone(row["per_core_WCET"])
            self.assertIsNone(row["performance_pass"])
            self.assertFalse(row["adopted"])
        self.assertFalse(self.result["receiver_adopted"])
        self.assertFalse(self.result["additional_software_decimation"])
        self.assertFalse(self.result["additional_software_requantization"])

    def test_recorded_results_reproduce(self):
        saved = json.loads((ROOT / "reports/s3-link-cpu-sensitivity/summary.json").read_text())
        overview = model.summary(self.result)
        for key, value in overview.items(): self.assertEqual(saved[key], value)
        data = json.dumps(self.result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(gzip.compress(data, mtime=0)).hexdigest(), saved["results_sha256"])


if __name__ == "__main__":
    unittest.main()

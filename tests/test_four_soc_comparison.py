import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("four_soc", ROOT / "experiments/four_soc_comparison.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FourSocComparisonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = m.load_inputs(ROOT / "reports/four-soc-comparison/inputs.json.gz")
        cls.result = m.compare(cls.inputs)

    def test_complete_ownership_and_cost_universe(self):
        self.assertEqual(self.result["coverage"], {"ownerships": 1280, "cost_profiles": 7040,
                         "distinct_ownership_pairs": 65536, "scenario_pair_records": 262144})
        for soc in m.SOC:
            pairs = [r for r in self.result["pairs"] if r["pair"][0].startswith(soc + "-") and r["scenario"] == [False, 100]]
            self.assertEqual(len({tuple(r["pair"]) for r in pairs}), 16384)

    def test_missing_and_duplicate_owners_are_rejected(self):
        bad = copy.deepcopy(self.inputs)
        bad["ownerships"][1]["owners"] = bad["ownerships"][0]["owners"].copy()
        with self.assertRaisesRegex(ValueError, "missing/duplicate ownership"):
            m.validate(bad)

    def test_cpu_omission_or_double_charge_is_rejected(self):
        bad = copy.deepcopy(self.inputs)
        bad["mode_profiles"][0]["profiles"][0]["CPU_Mcycles_s_before_boundary_drivers"] += 1
        with self.assertRaisesRegex(ValueError, "CPU accounting mismatch"):
            m.validate(bad)

    def test_separate_images_use_whole_mode_max_not_stage_union(self):
        # Different stages consume the same sites in mutually exclusive images.
        t = {k: 0 for k in m.CAP}; s = t.copy()
        t.update(logic_sites_estimate=6000, BSRAM=18)
        s.update(logic_sites_estimate=5500, BSRAM=22)
        self.assertEqual(m.separate_images(t, s), dict(logic_sites_estimate=6000, FF=0, BSRAM=22, DSP18=0))

    def test_estimated_failure_or_frontier_never_becomes_feasibility(self):
        self.assertTrue(any(p["declared_model_screen_pass"] for p in self.result["profiles"]))
        self.assertTrue(any(not p["declared_model_screen_pass"] for p in self.result["profiles"]))
        for p in self.result["profiles"]:
            self.assertFalse(p["performance_verified"])
            self.assertIsNone(p["whole_resources"])
            self.assertIsNone(p["per_core_WCET"])
            self.assertIsNone(p["communication_assignment"])
            self.assertEqual(set(p["unknown"]), set(m.UNKNOWN))
        self.assertTrue(self.result["hypothesis_comparison_ready"])
        self.assertFalse(self.result["best_candidate_certifiable"])
        self.assertFalse(self.result["receiver_adopted"])

    def test_checked_report_reproduces_exact_semantics(self):
        recorded = json.loads((ROOT / "reports/four-soc-comparison/summary.json").read_text())
        for key in recorded.keys() - {"files"}:
            self.assertEqual(recorded[key], self.result[key])
        encoded = gzip.compress(m.canonical(self.result), mtime=0)
        self.assertEqual(hashlib.sha256(encoded).hexdigest(),
                         recorded["files"]["reports/four-soc-comparison/comparison.json.gz"]["sha256"])


if __name__ == "__main__":
    unittest.main()

import gzip
import hashlib
import itertools
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments"))
from control_only_estimate import KEYS,read,rows
from shared_sdf_update import EVIDENCE,OLD_FFT,updated


class SharedSDFUpdateTests(unittest.TestCase):
    def test_every_ownership_remains_and_only_fft_changes_cost(self):
        for board in ("9k","20k"):
            old={r["id"]:r for r in rows(board)}
            new=updated(board)
            self.assertEqual(len(new),448)
            self.assertEqual({r["ownership_id"] for r in new},set(old))
            for r in new:
                original=old[r["ownership_id"]]
                self.assertEqual(r["flows"],original["flows"])
                self.assertEqual(r["CPU_before_driver_Mcycles_s"],original["CPU_before_driver_Mcycles_s"])
                self.assertIsNone(r["whole_performance_pass"])
                self.assertIsNone(r["whole_resources"])
                self.assertEqual(r["formal_routes"],[])
                self.assertFalse(r["adopted"])

    def test_original_fft_cost_matches_pinned_profiles(self):
        profiles=read("reports/four-soc-comparison/inputs.json.gz")["mode_profiles"]
        for r in profiles:
            if not r["id"].startswith("S3-T-"):continue
            for p in r["profiles"]:
                if not p["high"] and p["FPGA_MHz"]==125 and "FFT" in p["FPGA_stage_estimates"]:
                    self.assertEqual(p["FPGA_stage_estimates"]["FFT"],OLD_FFT)

    def test_every_pair_and_max_or_sum(self):
        for board in ("9k","20k"):
            accepted=[r for r in updated(board) if r["command_only_return_compatible"]]
            self.assertEqual(len(accepted),19)
            ts=[r for r in accepted if r["standard"]=="T"]
            ss=[r for r in accepted if r["standard"]=="S"]
            raw=gzip.decompress((EVIDENCE/f"updated-{board}"/"allowed-pairs.json.gz").read_bytes())
            actual={(r["T"],r["S"]):r for r in json.loads(raw)}
            self.assertEqual(len(actual),84)
            for t,s in itertools.product(ts,ss):
                r=actual[t["id"],s["id"]]
                for k in KEYS:
                    expected=max(t["stage_resources"][k],s["stage_resources"][k]) if board=="9k" else t["stage_resources"][k]+s["stage_resources"][k]
                    self.assertEqual(r["stage_resources"][k],expected)
                self.assertIsNone(r["performance_pass"])
                self.assertEqual(r["formal_routes"],[])

    def test_cad_sources_and_ram_accounting(self):
        for label in ("9k-hybrid","9k-hybrid-110","9k-resident","20k-hybrid","20k-resident"):
            r=json.loads((EVIDENCE/label/"summary.json").read_text())
            for name,digest in r["source_sha256"].items():
                self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)
            use=r["routed_utilization"]
            self.assertEqual(r["bsram"],use["BSRAM"]["used"])
            self.assertEqual(r["dsp18"],4)
            self.assertEqual(r["routed_logic_positions"],use["LUT4"]["used"]+use["ALU"]["used"])
            self.assertFalse(r["external_IO_delays_constrained"])
            self.assertFalse(r["qualified_receiver"])

    def test_negative_timing_results_retained(self):
        for label,expected in (("9k-hybrid",True),("9k-hybrid-110",False),
                               ("9k-resident",False),("20k-hybrid",True),("20k-resident",True)):
            r=json.loads((EVIDENCE/label/"summary.json").read_text())
            self.assertEqual(r["timing_target_pass"],expected)
            self.assertTrue(r["route_completed"])

    def test_new_b_budget_has_no_ram_reserve(self):
        r=json.loads((EVIDENCE/"updated-20k/summary.json").read_text())
        self.assertEqual(r["old_shared_RS_B_replacement"]["hybrid"],
                         dict(zip(KEYS,(20681,13512,46,34))))
        self.assertEqual(r["adoption_count"],0)


if __name__=="__main__":unittest.main()

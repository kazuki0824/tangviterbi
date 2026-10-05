#!/usr/bin/env python3
"""Run independent arithmetic, stream-equivalence and service tests for an RS candidate."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

parser = argparse.ArgumentParser()
parser.add_argument("--rtl", type=Path, required=True)
parser.add_argument("--syndrome-cycles", type=int, choices=(0, 4, 8, 16), required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
source = args.rtl.resolve()
performance = json.loads((root / "ci/performance.json").read_text())


class CandidateTests(unittest.TestCase):
    def run_bench(self, top, sources, parameters=()):
        with tempfile.TemporaryDirectory() as temp:
            program = str(Path(temp) / top)
            subprocess.run([
                "iverilog", "-g2012", "-s", top, *parameters, "-o", program,
                str(source), *sources,
            ], cwd=root, check=True)
            subprocess.run(["vvp", program], cwd=root, check=True, timeout=120)

    def test_arithmetic(self):
        self.run_bench("gf256_tb", ["experiments/gf256_constants_tb.sv"
                                   if args.syndrome_cycles == 0 else "tests/gf256_tb.sv"])

    def test_stream(self):
        self.run_bench("rs_equivalence_tb", [
            "tests/fixtures/rs_reference.sv", "tests/rs_equivalence_tb.sv",
        ])

    def test_service(self):
        deadline = int(performance["target_clock_mhz"] * 1e6 *
                       performance["rs_codeword_bytes"] * 8 /
                       performance["trellis_steps_per_second"])
        saving = (16 - args.syndrome_cycles) * performance["rs_codeword_bytes"]
        self.run_bench("rs_budget_tb", [
            "tests/fixtures/rs_reference.sv", "tests/rs_budget_tb.sv",
        ], [f"-Prs_budget_tb.MAX_CYCLES={deadline}",
            f"-Prs_budget_tb.EXPECTED_SAVING={saving}"])


if __name__ == "__main__":
    unittest.main(argv=[__file__], verbosity=2)

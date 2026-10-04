from pathlib import Path
import os
import json
import shutil
import subprocess
import tempfile
import unittest


class RtlTests(unittest.TestCase):
    def test_job_driver_selects_decoder_and_memory_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree("ci", root / "ci", ignore=shutil.ignore_patterns("__pycache__"))
            commands = root / "bin"
            commands.mkdir()
            for name in ("yosys", "nextpnr-himbaechel"):
                command = commands / name
                command.write_text("#!/bin/sh\nexit 0\n")
                command.chmod(0o755)
            env = {**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"]}
            for variant, params in (
                ("core-only", (0, 1, 1)), ("mem", (1, 1, 1)),
                ("viterbi-only", (0, 1, 0)), ("rs-only", (0, 0, 1)),
            ):
                subprocess.run([
                    "bash", "ci/run_pnr.sh", "9k", variant,
                ], cwd=root, env=env, check=True, stdout=subprocess.DEVNULL)
                script = (root / "build/synth.ys").read_text()
                for name, value in zip(("WITH_MEM", "WITH_VITERBI", "WITH_RS"), params):
                    self.assertIn(f"-set {name} {value}", script)
                self.assertIn("rtl/psram_ctrl.sv", script)
            result = subprocess.run([
                "bash", "ci/run_pnr.sh", "unsupported", "core-only",
            ], cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertEqual(result.returncode, 2)

    def test_main_and_diagnostic_variants_elaborate(self):
        with tempfile.TemporaryDirectory() as temp:
            for mem, vit, rs in ((0, 1, 1), (1, 1, 1), (0, 1, 0), (0, 0, 1)):
                subprocess.run([
                    "iverilog", "-g2012", "-s", "benchmark_top",
                    f"-Pbenchmark_top.WITH_MEM={mem}",
                    f"-Pbenchmark_top.WITH_VITERBI={vit}",
                    f"-Pbenchmark_top.WITH_RS={rs}",
                    "-o", str(Path(temp) / "top"),
                    *map(str, sorted(Path("rtl").glob("*.sv"))),
                ], check=True)

    def test_viterbi_banked_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            for width in (16, 10):
                program = str(Path(temp) / "metrics")
                subprocess.run([
                    "iverilog", "-g2012", "-s", "viterbi_metrics_tb",
                    f"-Pviterbi_metrics_tb.METRIC_W={width}", "-o", program,
                    "rtl/viterbi_k7_16acs.sv", "tests/viterbi_metrics_tb.sv",
                ], check=True)
                subprocess.run(["vvp", program], check=True, timeout=30)

    def test_rs_block_service_deadline(self):
        performance = json.loads(Path("ci/performance.json").read_text())
        deadline = int(performance["target_clock_mhz"] * 1e6 *
                       performance["rs_codeword_bytes"] * 8 /
                       performance["trellis_steps_per_second"])
        with tempfile.TemporaryDirectory() as temp:
            program = str(Path(temp) / "rs-budget")
            subprocess.run([
                "iverilog", "-g2012", "-s", "rs_budget_tb",
                f"-Prs_budget_tb.MAX_CYCLES={deadline}", "-o", program,
                "rtl/rs204_188_compact.sv", "tests/rs_budget_tb.sv",
            ], check=True)
            subprocess.run(["vvp", program], check=True, timeout=30)

    def test_controller_transactions(self):
        with tempfile.TemporaryDirectory() as temp:
            program = str(Path(temp) / "controller")
            subprocess.run([
                "iverilog", "-g2012", "-s", "memory_tb", "-o", program,
                "rtl/psram_ctrl.sv", "tests/memory_tb.sv",
            ], check=True)
            subprocess.run(["vvp", program], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()

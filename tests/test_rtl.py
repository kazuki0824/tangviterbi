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
                command.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{root / (name + ".args")}"\nexit 0\n')
                command.chmod(0o755)
            env = {**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"]}

            cases = (
                ("9k", "core-only", (0, 1, 1, 16), False),
                ("9k", "mem", (1, 1, 1, 16), False),
                ("9k", "viterbi-only", (0, 1, 0, 16), False),
                ("9k", "rs-only", (0, 0, 1, 16), False),
                ("9k", "core-32acs", (0, 1, 1, 32), False),
                ("9k", "mem-32acs", (1, 1, 1, 32), False),
                ("9k", "viterbi-32acs", (0, 1, 0, 32), False),
                ("9k", "core-32acs-rsconst", (0, 1, 1, 32), True),
                ("9k", "mem-32acs-rsconst", (1, 1, 1, 32), True),
                ("20k", "core-32acs", (0, 1, 1, 32), False),
                ("20k", "mem-32acs", (1, 1, 1, 32), False),
                ("20k", "viterbi-32acs", (0, 1, 0, 32), False),
                ("20k", "core-32acs-rsconst", (0, 1, 1, 32), True),
                ("20k", "mem-32acs-rsconst", (1, 1, 1, 32), True),
            )
            for board, variant, params, rsconst in cases:
                subprocess.run([
                    "bash", "ci/run_pnr.sh", board, variant,
                ], cwd=root, env=env, check=True, stdout=subprocess.DEVNULL)
                script = (root / "build/synth.ys").read_text()
                for name, value in zip(
                    ("WITH_MEM", "WITH_VITERBI", "WITH_RS", "VITERBI_ACS"), params
                ):
                    self.assertIn(f"-set {name} {value}", script)
                self.assertIn("rtl/psram_ctrl.sv", script)
                self.assertIn("rtl/viterbi_k7_32acs.sv", script)
                if rsconst:
                    self.assertIn("experiments/rs_syndrome_constants.sv", script)
                    self.assertNotIn("rtl/rs204_188_compact.sv", script)
                settings = json.loads((root / "ci/performance.json").read_text())
                pnr_args = (root / "nextpnr-himbaechel.args").read_text().splitlines()
                self.assertEqual(pnr_args[pnr_args.index("--seed") + 1], str(settings["pnr_seed"]))
                self.assertEqual(float(pnr_args[pnr_args.index("--freq") + 1]), settings["target_clock_mhz"])

            result = subprocess.run([
                "bash", "ci/run_pnr.sh", "unsupported", "core-only",
            ], cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertEqual(result.returncode, 2)
            subprocess.run([
                "bash", "ci/run_pnr.sh", "9k", "core-32acs",
            ], cwd=root, env=env, check=True, stdout=subprocess.DEVNULL)
            script = (root / "build/synth.ys").read_text()
            self.assertIn("synth_gowin -top benchmark_top", script)
            self.assertNotIn("synth_gowin ''", script)

    def test_main_and_diagnostic_variants_elaborate(self):
        with tempfile.TemporaryDirectory() as temp:
            for mem, vit, rs, acs in (
                (0, 1, 1, 16), (1, 1, 1, 16), (0, 1, 0, 16), (0, 0, 1, 16),
                (0, 1, 1, 32), (1, 1, 1, 32), (0, 1, 0, 32),
            ):
                subprocess.run([
                    "iverilog", "-g2012", "-s", "benchmark_top",
                    f"-Pbenchmark_top.WITH_MEM={mem}",
                    f"-Pbenchmark_top.WITH_VITERBI={vit}",
                    f"-Pbenchmark_top.WITH_RS={rs}",
                    f"-Pbenchmark_top.VITERBI_ACS={acs}",
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

    def test_viterbi_32acs_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            for width in (16, 10):
                program = str(Path(temp) / "metrics32")
                subprocess.run([
                    "iverilog", "-g2012", "-s", "viterbi32_metrics_tb",
                    f"-Pviterbi32_metrics_tb.METRIC_W={width}", "-o", program,
                    "rtl/viterbi_k7_32acs.sv", "tests/viterbi32_metrics_tb.sv",
                ], check=True)
                subprocess.run(["vvp", program], check=True, timeout=30)

    def test_gf256_all_operand_pairs(self):
        with tempfile.TemporaryDirectory() as temp:
            program = str(Path(temp) / "gf256")
            subprocess.run([
                "iverilog", "-g2012", "-s", "gf256_tb", "-o", program,
                "rtl/rs204_188_compact.sv", "tests/gf256_tb.sv",
            ], check=True)
            subprocess.run(["vvp", program], check=True, timeout=30)

    def test_rs_stream_matches_frozen_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            program = str(Path(temp) / "rs-equivalence")
            subprocess.run([
                "iverilog", "-g2012", "-s", "rs_equivalence_tb", "-o", program,
                "rtl/rs204_188_compact.sv", "tests/fixtures/rs_reference.sv",
                "tests/rs_equivalence_tb.sv",
            ], check=True)
            subprocess.run(["vvp", program], check=True, timeout=90)

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
                f"-Prs_budget_tb.EXPECTED_SAVING={(16-performance['rs_syndrome_cycles_per_byte'])*performance['rs_codeword_bytes']}",
                "rtl/rs204_188_compact.sv", "tests/fixtures/rs_reference.sv", "tests/rs_budget_tb.sv",
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

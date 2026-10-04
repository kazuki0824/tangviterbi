from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


class RtlTests(unittest.TestCase):
    def test_core_only_synthesis_scripts_identical(self):
        # Exercise the real job driver with dummy CAD binaries: this verifies
        # its generated synthesis inputs, not the CAD tools themselves.
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
            scripts = []
            for board in ("4k", "9k"):
                subprocess.run([
                    "bash", "ci/run_pnr.sh", board, "core-only",
                ], cwd=root, env=env, check=True, stdout=subprocess.DEVNULL)
                scripts.append((root / "build/synth.ys").read_text())
            self.assertEqual(scripts[0], scripts[1])
            self.assertIn("-set WITH_MEM 0 -set PSRAM 0", scripts[0])

    def test_main_and_diagnostic_variants_elaborate(self):
        with tempfile.TemporaryDirectory() as temp:
            for psram in (0, 1):
                for mem in (0, 1):
                    with self.subTest(psram=psram, mem=mem):
                        subprocess.run([
                            "iverilog", "-g2012", "-s", "benchmark_top",
                            f"-Pbenchmark_top.PSRAM={psram}",
                            f"-Pbenchmark_top.WITH_MEM={mem}",
                            "-o", str(Path(temp) / "top"),
                            *map(str, sorted(Path("rtl").glob("*.sv"))),
                        ], check=True)
            for vit, rs in ((1, 0), (0, 1)):
                subprocess.run([
                    "iverilog", "-g2012", "-s", "benchmark_top",
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

    def test_controller_transactions(self):
        with tempfile.TemporaryDirectory() as temp:
            program = str(Path(temp) / "controller")
            subprocess.run([
                "iverilog", "-g2012", "-s", "memory_tb", "-o", program,
                "rtl/hyperram_ctrl.sv", "rtl/psram_ctrl.sv", "tests/memory_tb.sv",
            ], check=True)
            subprocess.run(["vvp", program], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()

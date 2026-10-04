from pathlib import Path
import subprocess
import tempfile
import unittest


class RtlTests(unittest.TestCase):
    def test_four_variants_elaborate(self):
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

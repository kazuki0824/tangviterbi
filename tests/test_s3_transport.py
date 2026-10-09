"""Execute the real zero-copy C state machine, including two host threads."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TransportTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "C compiler required")
    def test_ring_concurrency_wire_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as out:
            exe = Path(out) / "transport"
            subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=undefined", "-fno-sanitize-recover=all", "-pthread",
                            "-I", str(ROOT / "experiments"),
                            str(ROOT / "experiments/s3_transport.c"),
                            str(ROOT / "tests/s3_transport_host.c"), "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=30)
        report = json.loads(result.stdout)
        self.assertTrue(report["all_pass"])
        self.assertEqual(report["payload_bytes_checked"], 40960000)
        dest = ROOT / "build/s3-transport"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "host.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main()

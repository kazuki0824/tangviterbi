import json
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class CaptureTest(unittest.TestCase):
    def test_wrapped_bank_packing_and_faults(self):
        with tempfile.TemporaryDirectory() as out:
            exe=Path(out)/"capture"
            subprocess.run(["cc","-std=c11","-O2","-Wall","-Wextra","-Werror",
                "-fsanitize=undefined","-fno-sanitize-recover=all","-I",str(ROOT/"experiments"),
                *[str(ROOT/p) for p in ("experiments/s3_transport.c","experiments/s3_capture_bridge.c",
                                        "tests/s3_capture_host.c")],"-o",str(exe)],check=True)
            d=json.loads(subprocess.check_output([str(exe)],text=True))
            self.assertTrue(d["all_pass"])
            self.assertGreater(d["checked_bytes"],2_000_000)
            dest=ROOT/"build/s3-capture";dest.mkdir(parents=True,exist_ok=True)
            (dest/"host.json").write_text(json.dumps(d,indent=2)+"\n")

from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class NativeCaptureTest(unittest.TestCase):
    def test_mmio_bank_handoff_and_forced_stop(self):
        out=ROOT/'build/s3-native-capture';out.mkdir(parents=True,exist_ok=True)
        command=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-DS3_RING_PAGE_COUNT=16','-I',str(ROOT/'experiments'),str(ROOT/'tests/s3_native_capture_host.c'),*[str(ROOT/'experiments'/p) for p in ('s3_native_capture.c','s3_capture_bridge.c','s3_transport.c')],'-o',str(out/'sim')]
        c=subprocess.run(command,text=True,capture_output=True);self.assertEqual(c.returncode,0,c.stderr)
        r=subprocess.run([str(out/'sim')],text=True,capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);(out/'result.txt').write_text(r.stdout)
if __name__=='__main__':unittest.main()

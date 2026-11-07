from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class NativeFillTest(unittest.TestCase):
    def test_all_origins_and_wraps(self):
        out=ROOT/'build/s3-native-fill';out.mkdir(parents=True,exist_ok=True)
        cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-I',str(ROOT/'experiments'),str(ROOT/'tests/s3_native_fill_host.c'),str(ROOT/'experiments/s3_capture_bridge.c'),str(ROOT/'experiments/s3_transport.c'),'-o',str(out/'test')]
        for unroll in (1,4,8):
            with self.subTest(unroll=unroll):
                r=subprocess.run(cmd+['-DS3_NATIVE_FILL_UNROLL='+str(unroll)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
                r=subprocess.run([str(out/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                print('unroll',unroll,r.stdout)
if __name__=='__main__':unittest.main()

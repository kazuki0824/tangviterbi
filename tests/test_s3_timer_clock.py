from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class TimerClockTest(unittest.TestCase):
    def test_actual_adapter_and_quantized_phases(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);flags=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-Iexperiments','-Itests/s3_sdk_shim']
            subprocess.run(flags+['-DESP_PLATFORM','-c','experiments/s3_timer_clock.c','-o',str(out/'timer.o')],cwd=ROOT,check=True)
            # ESP_PLATFORM exposes wrapper declarations in this test only; the
            # native MMIO assembly is not compiled into the host model.
            subprocess.run(flags+['-DESP_PLATFORM','-c','tests/s3_timer_clock_host.c','-o',str(out/'test.o')],cwd=ROOT,check=True)
            sources=['s3_native_capture.c','s3_parallel_capture.c','s3_parallel_pack.c','s3_capture_bridge.c','s3_transport.c']
            subprocess.run(flags+[str(out/'test.o'),str(out/'timer.o')]+['experiments/'+s for s in sources]+['-o',str(out/'test')],cwd=ROOT,check=True)
            r=subprocess.run([str(out/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(r.stdout)
if __name__=='__main__':unittest.main()

from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
class SerialTSTest(unittest.TestCase):
 def test_dual_stream(self):
  d=ROOT/"build/serial-ts";d.mkdir(parents=True,exist_ok=True)
  p=subprocess.run(["iverilog","-g2012","-s","tb","-o",str(d/"sim"),
    str(ROOT/"rtl/isdb_serial_ts_sink.sv"),str(ROOT/"tests/dual_serial_ts_tb.sv")],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
  r=subprocess.run(["vvp",str(d/"sim")],capture_output=True,text=True,timeout=30)
  (d/"run.log").write_text(r.stdout+r.stderr)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=="__main__":unittest.main()

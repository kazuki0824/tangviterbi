"""Fill both packet slots by withholding memory service, then release it."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_dual_s_frame_dma import BENCH,ROOT,reference

@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class SFrameHold(unittest.TestCase):
    def test_both_slots_full_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            for name,data in zip(('input','expected'),reference(1)):
                (p/f'{name}.hex').write_text('\n'.join(f'{x:02x}' for x in data)+'\n')
            (p/'tb.sv').write_text(BENCH.replace('qr=!active &&','qr=cycle>12000 && !active &&'))
            subprocess.run(['iverilog','-g2012','-s','tb','-Ptb.SUPERFRAMES=1','-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/dual_s_frame_dma.sv')],check=True,timeout=60)
            run=subprocess.run(['vvp',str(p/'sim')],cwd=p,capture_output=True,text=True,timeout=90)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            line=next(x for x in run.stdout.splitlines() if x.startswith('RESULT '))
            row={k:int(v) for k,v in (kv.split('=') for kv in line.split()[1:])}
            self.assertEqual(row['peak_packets'],2)
            self.assertGreater(row['input_stalls'],0)
            self.assertEqual(row['output_bytes'],78336)
            self.assertEqual(row['writes'],5040)
            self.assertEqual(row['reads'],2688)
            print(json.dumps(row),flush=True)
            if os.environ.get('DUAL_S_HOLD_REPORT'):
                files=[Path(__file__),ROOT/'tests/test_dual_s_frame_dma.py',ROOT/'rtl/dual_s_frame_dma.sv']
                Path(os.environ['DUAL_S_HOLD_REPORT']).write_text(json.dumps(dict(result=row,memory_initial_hold_clocks=12000,scope='Functional finite holding, not real-time admission',source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}),indent=2)+'\n')

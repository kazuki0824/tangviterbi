"""State/output equivalence of parallel row comparisons at relevant parameter sets."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(shutil.which('yosys'),'Yosys required')
class BankParallelTest(unittest.TestCase):
 def test_equivalence(self):
  for refresh,openpage in [(64,0),(64,1),(1203,1),(65535,1)]:
   with self.subTest(refresh=refresh,openpage=openpage),tempfile.TemporaryDirectory()as tmp:
    chunks=[]
    for filename,name in [('dual_sdram_refresh_predecode.sv','gold'),('dual_sdram_bank_parallel.sv','gate')]:
     chunks.append(f'''read_verilog -sv {ROOT}/experiments/{filename}
chparam -set REFRESH_CYCLES {refresh} -set OPEN_PAGE {openpage} dual_sdram_burst
proc
memory
rename dual_sdram_burst {name}
''')
    chunks.append('equiv_make gold gate equiv\nhierarchy -top equiv\nequiv_simple\nequiv_induct -seq 4\nequiv_status -assert\n')
    p=Path(tmp)/'equiv.ys';p.write_text('\n'.join(chunks))
    r=subprocess.run(['yosys','-Q','-s',str(p)],capture_output=True,text=True,timeout=120)
    print(f'REFRESH={refresh} OPEN_PAGE={openpage}\n'+r.stdout,flush=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)

"""Cycle equivalence of fixed-context metadata against the saved original reader."""
import hashlib,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
from tests.test_t_soft_reader import TB
ROOT=Path(__file__).resolve().parents[1]
REFERENCE=ROOT/'experiments/reference_t_soft_reader.sv'
EXTRA=r'''
wire bcr;wire[1:0]blive;wire breuse,bqv,brr,bsv,bfault;
wire[20:0]bqa;wire[1:0]bsc;wire[7:0]bsd;
reference_t_soft_reader baseline(clk,resetn,cv,bcr,ca,cl,blive,breuse,
 bqv,qr,bqa,rv,brr,rd,bsv,sr,bsc,bsd,bfault);
always @(negedge clk)begin
 #2;if(cycle>2 && {cr,live,reuse,qv,rr,sv,fault,qa,sc,sd}!==
                 {bcr,blive,breuse,bqv,brr,bsv,bfault,bqa,bsc,bsd})
  $fatal(1,"reader trace mismatch at cycle %0d",cycle);
end
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ReaderEquivalenceTest(unittest.TestCase):
 def test_fixed_context_cycle_trace(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(TB.replace('endmodule',EXTRA+'\nendmodule'))
   subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(p/'tb.sv'),str(REFERENCE),str(ROOT/'rtl/t_soft_reader.sv')],check=True)
   r=subprocess.run(['vvp',str(p/'sim')],text=True,capture_output=True,timeout=30)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS symbols=40',r.stdout);print(r.stdout.strip())
  if os.environ.get('T_SOFT_EQUIVALENCE_REPORT'):
   files=[Path(__file__),ROOT/'tests/test_t_soft_reader.py',REFERENCE,ROOT/'rtl/t_soft_reader.sv']
   Path(os.environ['T_SOFT_EQUIVALENCE_REPORT']).write_text(json.dumps(dict(scope=__doc__,summary=r.stdout.strip(),source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()for f in files},formal_equivalence=False),indent=2)+'\n')

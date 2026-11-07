import hashlib,json,math,subprocess,tempfile,unittest
from pathlib import Path
from experiments.s3_joint_runtime import ROOT
class Counters(unittest.TestCase):
 def test_source_provenance(self):
  r=json.loads((ROOT/'reports/s3-counter-envelope/instructions.json').read_text())
  for p,h in r['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),h)
  self.assertEqual(r['paths']['take_all']['instructions'],55)
  self.assertEqual(r['paths']['take_empty']['instructions'],30)
  self.assertEqual(r['paths']['complete_all']['instructions'],153)
  self.assertEqual(r['extra_complete_instructions'],9)
 def test_actual_c_all_completion_orders_across_counter_carry(self):
  with tempfile.TemporaryDirectory() as tmp:
   for chunk in (16384,32768):
    binary=str(Path(tmp)/'probe')
    subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Wno-misleading-indentation','-fsanitize=undefined','-fno-sanitize-recover=all',f'-DS3_RAW_TRANSFER_BYTES={chunk}',f'-I{ROOT/"experiments"}',str(ROOT/'tests/s3_counter_boundaries.c'),str(ROOT/'experiments/s3_parallel_pack.c'),'-o',binary],check=True)
    r=json.loads(subprocess.check_output([binary],text=True));self.assertEqual(r['completion_orders'],8*sum(math.factorial(i) for i in range(1,r['leases']+1)))
    print(r)
if __name__=='__main__':unittest.main()

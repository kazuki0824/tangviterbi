import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
from experiments.s3_joint_runtime import ROOT
class InlinePack(unittest.TestCase):
 def test_candidate_is_identical_bit_mapping(self):
  old=(ROOT/'experiments/s3_iq10_block.h').read_text()
  new=(ROOT/'experiments/s3_iq10_inline.h').read_text()
  self.assertEqual(old[old.index('{'):],new[new.index('{'):])
 def test_target_evidence(self):
  j=json.loads((ROOT/'reports/s3-inline-packing/instructions.json').read_text())
  for p,h in j['source_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),h)
  rows={(r['variant'],r['optimization']):r for r in j['rows']}
  self.assertEqual(rows['baseline','O2']['total_per_eight_samples'],45)
  self.assertEqual(rows['inline','O2']['total_per_eight_samples'],39)
  self.assertFalse(j['full_slice_cost_audited'])
 def test_concurrent_actual_candidate_all_splits_and_transfer_sizes(self):
  with tempfile.TemporaryDirectory() as tmp:
   for share,chunk in ((5,16384),(6,16384),(8,32768)):
    for opt in ('-O2','-Os'):
     exe=Path(tmp)/'inline'
     subprocess.run(['cc','-std=c11',opt,'-Wall','-Wextra','-Werror','-pthread','-fsanitize=undefined','-fno-sanitize-recover=all',f'-DS3_PP_CORE0_SIXTEENTHS={share}',f'-DS3_RAW_TRANSFER_BYTES={chunk}','-Iexperiments','experiments/s3_inline_pack.c','tests/s3_parallel_pack_host.c','-o',str(exe)],cwd=ROOT,check=True)
     r=subprocess.run([str(exe),'2000'],text=True,capture_output=True,check=True);print(share,chunk,opt,r.stdout.strip())
if __name__=='__main__':unittest.main()

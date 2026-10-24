"""Count paths in an instrumented copy of real C; never use host timing as S3 WCET."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run():
 src=ROOT/'experiments/s3_parallel_pack.c';original=src.read_text();text=original
 edits=[('   const uint32_t *src=b->words+input;','   ++s3_audit_stats[s3_audit_owner][0];s3_audit_stats[s3_audit_owner][1]+=blocks;\n   const uint32_t *src=b->words+input;'),('   uint32_t a=word(b,logical),c=word(b,logical+1);','   ++s3_audit_stats[s3_audit_owner][2];\n   uint32_t a=word(b,logical),c=word(b,logical+1);')]
 for old,new in edits:
  if text.count(old)!=1:raise RuntimeError('instrumentation site changed')
  text=text.replace(old,new)
 text='extern unsigned long long s3_audit_stats[2][5];\nextern unsigned s3_audit_owner;\n'+text
 with tempfile.TemporaryDirectory() as tmp:
  path=Path(tmp);(path/'instrumented.c').write_text(text)
  subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'experiments'),str(path/'instrumented.c'),str(ROOT/'experiments/s3_pack_path_probe.c'),'-o',str(path/'probe')],check=True)
  rows=json.loads(subprocess.check_output([str(path/'probe')],text=True))
 checks=[]
 for r in rows:
  total=r['banks']*r['bank_samples'];r['full_output_offset_cycle']=r['bank_samples']==12288
  checks.append(dict(name=str([r[k] for k in ('bank_samples','first','slice_pairs')]),passed=sum(4*s[1]+s[2] for s in r['stats'])==total//2 and all(s[4]==2*s[3] for s in r['stats'])))
  r['rates']={}
  for name,rate in [('T',16e6),('S',40e6)]:
   cores=[]
   for s in r['stats']:
    scale=rate/total;cores.append(dict(zip(['runs_s','blocks_s','slow_pairs_s','slices_s','clock_reads_s'],[v*scale for v in s])))
   r['rates'][name]=cores
 return dict(scope=__doc__,counter_order=['runs','eight_sample_blocks','slow_pairs','slices','clock_reads'],rows=rows,checks=checks,source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),instrumented_source_sha256=hashlib.sha256(text.encode()).hexdigest(),limitations=['64 banks per declared case; only 12288 case covers full output-offset period','Workers are sequential, DMA immediately completes and artificial clock always returns zero','Actual C output checked byte-for-byte after every bank','Rates assume sustained constant input sample rate and declared bank/slice pattern','No core binding, wall-clock performance, RF timing, idle/empty polling or interrupt model'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(cases=len(r['rows']),checks=len(r['checks']),failed=sum(not c['passed'] for c in r['checks']))));raise SystemExit(any(not c['passed'] for c in r['checks']))

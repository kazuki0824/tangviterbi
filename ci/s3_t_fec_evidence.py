#!/usr/bin/env python3
"""Freeze actual T FEC/physical-memory partial fit evidence, including failures."""
import argparse,gzip,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--reuse',action='store_true',help='Freeze existing matching measurements without rerunning CAD')
 a=p.parse_args();out=ROOT/'reports/s3-t-fec-evidence';out.mkdir(parents=True,exist_ok=True)
 results={}
 for compact,name in ((False,'s3-memory-fec-T-rr-90MHz'),(True,'s3-memory-fec-compact-T-b1-rs-rr-90MHz')):
  b=ROOT/'build'/(name+'-pnr');dest=out/('compact' if compact else 'baseline');dest.mkdir(exist_ok=True)
  command=[sys.executable,'ci/s3_psram_benchmark.py','--terrestrial-fec','--rr-table',
           '--core-mhz','90','--seeds','1','--pnr-timeout','180']
  if compact:command.append('--compact-rs')
  if not a.reuse:subprocess.run(command,cwd=ROOT,check=True)
  r=json.loads((b/'result.json').read_text())
  for source,expected in r['sources'].items():
   if hashlib.sha256((ROOT/source).read_bytes()).hexdigest()!=expected:raise ValueError('stale source: '+source)
  # Independently encode/inject each exact RS source measured by CAD.
  with (dest/'rs-test.log').open('w') as f:
   subprocess.run([sys.executable,'experiments/check_isdb_rs.py','--rtl',str(b/'rs.sv'),
    '--output',str(dest/'rs-vectors.json'),'--max-cycles','2667' if compact else '2666'],
    cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
  for file in ('viterbi.sv','rs.sv','queue.sv','clock.sv','synth.log','pack-only.log','pnr.log'):
   (dest/(file+'.gz')).write_bytes(gzip.compress((b/file).read_bytes(),mtime=0))
  for file in ('result.json','logic-site-audit.json','stat.json','synth.ys','pins.cst','clocks.py'):
   shutil.copy2(b/file,dest/file)
  results['compact' if compact else 'baseline']=dict(command=command[1:],
   logic_site_audit=r['logic_site_audit'],pnr_trials=r['pnr_trials'],
   RS=json.loads((dest/'rs-vectors.json').read_text()))
 env=dict(os.environ,PYTHONPATH=str(ROOT/'tests'))
 prior=ROOT/'build/t-fec-unittest.txt'
 if a.reuse and prior.exists() and prior.read_text().rstrip().endswith('OK'):
  shutil.copy2(prior,out/'unittest.txt')
 else:
  with (out/'unittest.txt').open('w') as f:
   subprocess.run([sys.executable,'-m','unittest','-v','test_s3_viterbi_decode','test_s3_rs_compact'],
    cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
 for name in ('decode-modulo13-pipe.json','reset-oracle.json','metric-oracle.json'):
  source=ROOT/'build/s3-viterbi'/name
  if source.exists():shutil.copy2(source,out/name)
 sources=['ci/s3_t_fec_evidence.py','ci/s3_psram_benchmark.py','experiments/s3_memory_t_fec_benchmark.sv',
          'experiments/s3_viterbi_traceback.py','experiments/s3_rs_isdb.py','experiments/check_isdb_rs.py']
 result=dict(scope=__doc__,source_sha256={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources},
  variants=results,whole_receiver_resources_verified=False,whole_receiver_deadlines_verified=False,
  receiver_adopted=False,safe_to_flash=False,
  absent=['FIR','synchronization/GI removal','FFT','equalization/demap','all interleavers',
          'actual FEC stream coupling','TS scheduler','external IO STA'])
 (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:dict(minimum_sites=v['logic_site_audit']['minimum_required_logic_sites'],
  CAD_exit_codes=[t['exit_code'] for t in v['pnr_trials']],RS_pass=v['RS']['all_pass']) for k,v in results.items()},indent=2))

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Freeze FPGA precision/RPC-guard results and every failed P&R seed."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ci'))
from s3_logic_site_audit import audit

def main():
 out=ROOT/'reports/s3-precision-evidence';out.mkdir(parents=True,exist_ok=True)
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 result=dict(scope=__doc__,receiver_adopted=False,safe_to_flash=False,profiles={},tests={},sources={})
 for name in ('s3-precision-tests.log','s3-rs-rpc-guard-tests.log','s3-rs-rpc-guard-cdc-tests.log'):
  p=ROOT/'build'/name;t=p.read_text()
  if not t.rstrip().endswith('OK'):raise ValueError('failed or unfinished tests: '+name)
  shutil.copy2(p,out/name)
 base='s3-memory-fec-compact-b1-q15-folded'
 names=[base+f'-shift{s}-rs-offload-correct-syready-rr-90MHz' for s in (23,24,25)]
 names += [base+middle+'-rs-offload-correct-rpcguard-syready-rr-90MHz' for middle in ('','-shift24')]
 names += [base+'-shift24-rs-offload-correct-rpcguard-rpcflag-syready-rr-90MHz']
 names += [base+'-shift24-rs-offload-correct-rpcguard-rpcflag-rpcranges-syready-rr-90MHz']
 names += [base+'-shift24-rs-offload-correct-rpcguard-rpcflag-rpcranges-rpc27-syready-rr-90MHz']
 names += [base+'-rs-offload-correct-rpcguard-rpcflag-rpcranges-rpc27-syready-rr-90MHz']
 for name in names:
  build=ROOT/f'build/{name}-pnr';r=json.loads((build/'result.json').read_text())
  for source,h in r['sources'].items():
   if sha(ROOT/source)!=h:raise ValueError('stale P&R source: '+source)
  site=audit(build/'packed.json')
  if site!=r['logic_site_audit']:raise ValueError('stale site audit: '+name)
  u=r.get('utilization')
  if u:
   site['actual_routed_logic_sites']=u['LUT4']['used']+u['ALU']['used']
   site['actual_routed_logic_site_percent']=site['actual_routed_logic_sites']*100/8640
  result['profiles'][name]=dict(report=r,audit=site)
  dest=out/name;dest.mkdir(exist_ok=True)
  for f in ('metric.sv','viterbi.sv','top.sv','syndrome.sv','guard.sv','queue.sv','clock.sv','synth.ys','clocks.py','pins.cst','pack-only.log','stat.json'):
   if (build/f).exists():shutil.copy2(build/f,dest/f)
  for pattern in ('pnr-seed*.log','report-seed*.json'):
   for f in build.glob(pattern):shutil.copy2(f,dest/f.name)
  if (build/'trials').exists():
   shutil.copytree(build/'trials',dest/'trials',dirs_exist_ok=True,
                   ignore=shutil.ignore_patterns('synth.log'))
 test_names=[f's3-precision-metric-{s}' for s in (22,23,24,25)]
 test_names += [f's3-precision-acs-{s}' for s in (23,24,25)]
 test_names += ['s3-precision-ber','s3-rs-rpc-guard','s3-rs-rpc-guard-registered','s3-rs-rpc-guard-registered-ranges','s3-rs-rpc-guard-cdc']
 for name in test_names:
  build=ROOT/'build'/name;r=json.loads((build/'result.json').read_text())
  if r.get('result') not in ('pass','completed'):raise ValueError('bad test result: '+name)
  for source,h in r.get('sources',{}).items():
   path=ROOT/source if '/' in source else build/source
   if sha(path)!=h:raise ValueError('stale simulation source: '+str(path))
  result['tests'][name]=r
  dest=out/name;dest.mkdir(exist_ok=True)
  for pattern in ('*.sv','result.json','simulation.log'):
   for f in build.glob(pattern):shutil.copy2(f,dest/f.name)
 patterns=('experiments/s3_tc8psk*.py','experiments/s3_viterbi_traceback.py','experiments/s3_rs_rpc_guard_registered.py',
  'rtl/s3_tc8psk_metric_folded.sv','rtl/s3_rs_rpc_guard*.sv','tests/test_s3_tc8psk_precision.py',
  'tests/test_s3_rs_rpc_guard*.py','ci/s3_precision*.py','ci/s3_psram_benchmark.py',
  '.github/workflows/s3-receiver-offline.yml')
 files={p for pattern in patterns for p in ROOT.glob(pattern)}
 result['sources']={str(p.relative_to(ROOT)):sha(p) for p in sorted(files)}
 (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({name:dict(exit_code=r['report']['exit_code'],sites=r['audit'].get('actual_routed_logic_sites'))
                   for name,r in result['profiles'].items()},indent=2))

if __name__=='__main__':main()

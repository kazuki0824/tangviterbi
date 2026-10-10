#!/usr/bin/env python3
"""Freeze RS split evidence, including failed timing seeds; reject stale inputs."""
from pathlib import Path
import argparse,hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ci'))
from s3_logic_site_audit import audit
p=argparse.ArgumentParser();p.add_argument('--test-log',type=Path,required=True)
p.add_argument('--additional-test-log',type=Path,action='append',default=[]);a=p.parse_args()
out=ROOT/'reports/s3-rs-offload-evidence';out.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r=dict(receiver_adopted=False,safe_to_flash=False,scope='Partial RS split/transport, not a receiver',
 profiles={},test_logs={},tests={},sources={})
for log in [a.test_log,*a.additional_test_log]:
 text=log.read_text()
 if not text.rstrip().endswith('OK'):raise ValueError('test suite incomplete/failed: '+str(log))
 shutil.copy2(log,out/log.name);r['test_logs'][log.name]=dict(sha256=sha(log),tail=text.splitlines()[-5:])
base='s3-memory-fec-compact-b1-q15-folded-rs-offload'
for suffix in ('','-rr','-rr-90MHz','-correct-rr-90MHz','-correct-syready-rr-90MHz','-correct-sy4-rr-90MHz'):
 name=base+suffix;build=ROOT/f'build/{name}-pnr'
 d=json.loads((ROOT/f'reports/{name}.json').read_text())
 for source,h in d['sources'].items():
  if sha(ROOT/source)!=h:raise ValueError('stale P&R source: '+source)
 site=audit(build/'packed.json')
 if site!=d['logic_site_audit']:raise ValueError('stale site audit: '+name)
 u=d.get('utilization')
 if u:
  site['actual_routed_logic_sites']=u['LUT4']['used']+u['ALU']['used']
  site['actual_routed_logic_site_percent']=site['actual_routed_logic_sites']*100/8640
 r['profiles'][name]=dict(report=d,audit=site)
 dest=out/name;dest.mkdir(exist_ok=True)
 for f in ('viterbi.sv','top.sv','syndrome.sv','queue.sv','clock.sv','synth.ys','clocks.py','pins.cst','pack-only.log','stat.json'):
  if (build/f).exists():shutil.copy2(build/f,dest/f)
 for pattern in ('pnr-seed*.log','report-seed*.json'):
  for f in build.glob(pattern):shutil.copy2(f,dest/f.name)
for name,src in (
 ('host-vectors','s3-rs-offload/result.json'),('RPC','s3-rs-rpc/result.json'),
 ('DDR_90_MHz','s3-psram-pipeline-90-rr/result.json')):
 d=json.loads((ROOT/'build'/src).read_text());r['tests'][name]=d
 (out/(name+'.json')).write_text(json.dumps(d,indent=2)+'\n')
for name,src in (
 ('syndrome','s3-rs-split-syndrome/simulation.log'),('registered_syndrome','s3-rs-split-syndrome-registered/simulation.log'),
 ('four_port_syndrome','s3-rs-split-syndrome-four-port/simulation.log'),
 ('Chien','s3-rs-split-chien/simulation.log'),('correction','s3-rs-correction/simulation.log'),
 ('arbitration','s3-psram-arbitration/simulation.log'),('workspace','s3-rs-workspace/test.log')):
 text=(ROOT/'build'/src).read_text()
 if 'PASS' not in text or 'FATAL' in text:raise ValueError('failed simulation: '+src)
 r['tests'][name]=text;(out/(name+'.log')).write_text(text)
target=json.loads((out/'target-compile.json').read_text())
for source,h in target['sources'].items():
 if sha(ROOT/source)!=h:raise ValueError('stale target object: '+source)
r['target_compile']=target
r['bandwidth']=json.loads((ROOT/'reports/s3-rs-offload-budget.json').read_text())
paths=set()
for pattern in ('experiments/s3_rs_offload*','experiments/s3_rs_rpc*','experiments/s3_rs_workspace*',
 'experiments/s3_rs_syndrome_*.py','experiments/s3_psram_queue_rotated.py',
 'experiments/s3_memory_rs_split_benchmark.sv','rtl/s3_rs_*.sv','tests/test_s3_rs_*.py',
 'tests/test_s3_psram_arbitration.py','tests/test_s3_psram_pipeline.py','ci/s3_rs_offload*',
 'ci/s3_psram_benchmark.py','.github/workflows/s3-receiver-offline.yml'):
 paths.update(ROOT.glob(pattern))
r['sources']={str(f.relative_to(ROOT)):sha(f) for f in sorted(paths) if f.is_file()}
(out/'results.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:dict(exit_code=v['report']['exit_code'],sites=v['audit'].get('actual_routed_logic_sites')) for k,v in r['profiles'].items()},indent=2))

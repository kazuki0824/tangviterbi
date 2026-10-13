#!/usr/bin/env python3
"""Reproduce the BM/Omega partition's standalone FPGA Forney evidence."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ci'))
from s3_area_benchmark import synth

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--co-placement',action='store_true')
 args=parser.parse_args()
 out=ROOT/'reports/s3-rs-forney-evidence';out.mkdir(parents=True,exist_ok=True)
 env=dict(os.environ,PYTHONPATH=str(ROOT/'tests'))
 with (out/'unittest.txt').open('w') as log:
  subprocess.run([sys.executable,'-m','unittest','-v','test_s3_rs_forney','test_s3_rs_offload'],
   cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
 area=synth(['rtl/s3_rs_forney.sv'],'s3_rs_forney',ROOT/'build/s3-rs-forney/area',narrow=True)
 measured=json.loads((ROOT/'build/s3-rs-forney/result.json').read_text())
 host=json.loads((ROOT/'build/s3-rs-offload/result.json').read_text())
 result=dict(scope='Standalone FPGA Forney and host GF operation counts; not whole-design P&R or silicon WCET',
  source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
   ('rtl/s3_rs_forney.sv','tests/test_s3_rs_forney.py','tests/test_s3_rs_offload.py','experiments/s3_rs_offload.c')},
  arithmetic=measured,synthesis=area,
  at_90_MHz=dict(service_us=587/90,capacity_codewords_s=90e6/587,
   conservative_arrival_codewords_s=28.86e6*2/(203*8),
   utilization_percent=100*587*(28.86e6*2/(203*8))/90e6),
  CPU_operation_count_correction='Successful Forney and rejected-position validation now counted separately',
  maximum_observed_host_operations={stage:{field:max(row[stage][field] for row in host['tests'])
   for field in ('mul_calls','mul_nonzero','div_calls','chien_steps')}
   for stage in ('bm_omega','chien','forney_with_locator_validation','rejected_position_validation')},
  FPGA_internal_timing_verified=False,whole_FPGA_resources_verified=False,
  CPU_WCET_verified=False,receiver_adopted=False,safe_to_flash=False)
 if args.co_placement:
  command=[sys.executable,'ci/s3_psram_benchmark.py','--rs-forney','--rpc-clock27',
   '--syndrome-ready','--rr-table','--core-mhz','90','--seeds','3','--pnr-timeout','180']
  subprocess.run(command,cwd=ROOT,check=True)
  name='s3-memory-fec-compact-b1-q15-folded-rs-offload-forney-correct-rpcguard-rpcflag-rpcranges-rpc27-syready-rr-90MHz-pnr'
  build=ROOT/'build'/name
  result['co_placement']=json.loads((build/'result.json').read_text())
  result['co_placement_command']=command[1:]
  for file in ('top.sv','viterbi.sv','guard.sv','queue.sv','clock.sv','syndrome.sv','synth.log','pack-only.log'):
   (out/(file+'.gz')).write_bytes(gzip.compress((build/file).read_bytes(),mtime=0))
  shutil.copy2(build/'logic-site-audit.json',out/'co-placement-site-audit.json')
 (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 for source in ('stat.json','synth.ys'):
  shutil.copy2(ROOT/'build/s3-rs-forney/area'/source,out/source)
 (out/'synth.log.gz').write_bytes(gzip.compress((ROOT/'build/s3-rs-forney/area/synth.log').read_bytes(),mtime=0))
 print(json.dumps(result,indent=2))

if __name__=='__main__':main()

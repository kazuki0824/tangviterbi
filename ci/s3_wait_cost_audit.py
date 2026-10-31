"""Exact incremental instruction counts of hardware polling loops; no invented iteration cap."""
import argparse,hashlib,json
from pathlib import Path
from ci.s3_sdk_cost_audit import Binary,ROOT
from ci.s3_receiver_cost_audit import bounded

def audit(tc):
 b=Binary(tc);items={}
 specs=[('spi_update','spi_hal_user_start',[(0x1a,0x15)],18,[3]),
        ('systimer','systimer_hal_get_counter_value',[(0x1e,0x18),(0x3d,0x30)],26,[3,6])]
 for name,fn,edges,base,coeff in specs:
  # Independent bounded CFG evaluation validates the affine formula.
  import itertools
  checks=[]
  for counts in itertools.product((0,1,2,8,16),repeat=len(edges)):
   r=bounded(b,fn,backedges=dict(zip(edges,counts)))
   predicted=base+sum(a*n for a,n in zip(coeff,counts))
   assert r['instructions']==predicted,(name,counts,r['instructions'],predicted)
   checks.append({'extra_iterations':counts,'instructions':r['instructions']})
  items[name]={'function':fn,'base_instructions_already_charged':base,'extra_instructions_per_iteration':coeff,'iteration_upper_bound':None,'checks':checks}
 return {'loops':items,'hardware_wcet':False,'conditions':['Instruction counts only; memory/MMIO latency and register window exceptions remain separate.','SDK loops have no software iteration cap. Coefficients are not finite worst-case latency bounds.','Snapshot retry does not repeat counter capture; do not multiply capture cost by snapshot retries.'], 'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),ROOT/'ci/s3_sdk_cost_audit.py',ROOT/'ci/s3_receiver_cost_audit.py')}}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--toolchain',type=Path,required=True);args=ap.parse_args();r=audit(args.toolchain.resolve());p=ROOT/'reports/s3-wait-cost';p.mkdir(exist_ok=True);(p/'instructions.json').write_text(json.dumps(r,indent=2)+'\n');print(r['loops'])

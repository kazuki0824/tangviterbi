"""All CFG branches of lease counters, under the eight outstanding lease invariant."""
import argparse, hashlib, json
from pathlib import Path
from ci.s3_sdk_cost_audit import Binary, ROOT
from ci.s3_receiver_cost_audit import bounded

def audit(tc):
 b=Binary(tc)
 paths={'take_all':bounded(b,'s3_pp_take'),
        'take_empty':bounded(b,'s3_pp_take',blocked=[0x4c]),
        'complete_all':bounded(b,'s3_pp_complete',backedges={(0x7a,0x51):8})}
 old=json.loads((ROOT/'reports/s3-sdk-cost-ledger/results.json').read_text())
 return {'paths':paths,'old_take':old['paths']['take_done']['own_instructions'],
         'old_complete':old['paths']['complete_8']['own_instructions'],
         'extra_complete_instructions':paths['complete_all']['instructions']-old['paths']['complete_8']['own_instructions'],
         'conditions':['At most eight outstanding leases; each retirement frees a distinct slot and increments retired.',
           'No unsigned 64-bit byte/sequence counter overflow; low 32-bit carry and unequal high words are allowed.',
           'CFG branch correlations are relaxed. Nine additional instructions may describe an infeasible ninth slot check, so the result is an envelope, not an observed path.',
           'No register-window trap or memory stall cycles included.'],
         'hardware_wcet':False,
         'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'ci/s3_receiver_cost_audit.py',ROOT/'ci/s3_sdk_cost_audit.py',ROOT/'experiments/s3_parallel_pack.c',ROOT/'reports/s3-sdk-cost-ledger/results.json']}}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--toolchain',type=Path,required=True);args=ap.parse_args()
 r=audit(args.toolchain.resolve());(ROOT/'reports/s3-counter-envelope/instructions.json').write_text(json.dumps(r,indent=2)+'\n')
 print({k:v['instructions'] for k,v in r['paths'].items()})

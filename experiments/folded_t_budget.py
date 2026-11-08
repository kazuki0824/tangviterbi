"""Overlay measured T kernels on all 448 existing variants, per CAD scenario.

Other blocks remain estimates. Costs already reserved in the old budget are
not added again; omitted integration/context cost is NOT silently set to zero.
No performance candidate is adopted solely from this arithmetic replacement.
"""
import argparse,copy,gzip,hashlib,itertools,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'reports/folded-t-evidence'
KEYS=('logic_sites_estimate','FF','BSRAM','DSP18')
CAPS={'9k':dict(zip(KEYS,(8640,6480,26,20))),'20k':dict(zip(KEYS,(20736,15552,46,48)))}
OLD=dict(zip(KEYS,(2952,1502,2,0)))
T_STEPS=4992*6*(7/8)/1039.5

def read(p):
 b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def write_gzip(p,obj):p.write_bytes(gzip.compress((json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode(),mtime=0))
def occupancy(r,b):return {k:100*r[k]/CAPS[b][k] for k in KEYS}

def update(board):
 oldpath=ROOT/f'reports/shared-sdf-evidence/updated-{board}/ownership-variants.json.gz'
 originals=read(oldpath);cases=[]
 for p in sorted(EVIDENCE.glob(f'{board}-*/summary.json')):
  proof=read(p);trial=p.parent.name
  resources=dict(zip(KEYS,(proof['logic_positions'],proof['FF'],proof['BSRAM'],proof['utilization']['MULT18X18']['used'])))
  rows=[];changed=0
  for original in originals:
   row=copy.deepcopy(original)
   if row['standard']=='T' and row['owners']['Viterbi']=='FPGA':
    changed+=1
    row['stage_resources']={k:row['stage_resources'][k]-OLD[k]+resources[k] for k in KEYS}
    row['stage_occupancy_percent']=occupancy(row['stage_resources'],board)
    row['T_kernel_measured_resources']=resources
    row['T_kernel_required_MHz']=T_STEPS*proof['cycles_per_step']
    row['T_kernel_target_MHz']=proof['target_MHz']
    row['T_kernel_arithmetic_utilization_percent']=100*row['T_kernel_required_MHz']/proof['target_MHz']
    row['T_kernel_target_pass']=proof['partial_target_pass']
    row['T_kernel_erasure_support']=proof.get('erasures',False)
    row['T_kernel_hierarchy_context_verified']=False
    row['resource_scope']='FFT and one-context T kernel measured separately; remaining costs inherited, incomplete'
    row['reasons']=[v for v in row['reasons'] if v!='REPLACEMENT_BUDGET_EXCEEDS_DEVICE']
    if any(row['stage_resources'][k]>CAPS[board][k] for k in KEYS):row['reasons'].append('REPLACEMENT_BUDGET_EXCEEDS_DEVICE')
    if not proof['partial_target_pass']:row['reasons'].append('T_KERNEL_TARGET_NOT_PASSED')
    if not proof.get('erasures',False):row['reasons'].append('T_KERNEL_ZERO_WEIGHT_ERASURES_NOT_IMPLEMENTED')
   row.update(formal_routes=[],adopted=False,whole_performance_pass=None,whole_resources=None)
   rows.append(row)
  ts=[r for r in rows if r['standard']=='T' and r['command_only_return_compatible']]
  ss=[r for r in rows if r['standard']=='S' and r['command_only_return_compatible']]
  pairs=[]
  for t,s in itertools.product(ts,ss):
   r={k:(max(t['stage_resources'][k],s['stage_resources'][k]) if board=='9k' else t['stage_resources'][k]+s['stage_resources'][k]) for k in KEYS}
   pairs.append(dict(T=t['id'],S=s['id'],stage_resources=r,stage_occupancy_percent=occupancy(r,board),
      aggregation='separate_images_max' if board=='9k' else 'simultaneous_sum',
      performance_pass=None,formal_routes=[],adopted=False,whole_resources=None))
  raw=next(r for r in rows if r['id']=='S3-T-000:hybrid')
  case=dict(trial=trial,proof=f'reports/folded-t-evidence/{trial}/summary.json',
   measured_kernel=resources,cycles_per_step=proof['cycles_per_step'],
   required_MHz=T_STEPS*proof['cycles_per_step'],target_MHz=proof['target_MHz'],
   arithmetic_utilization_percent=100*T_STEPS*proof['cycles_per_step']/proof['target_MHz'],
   routed_fmax_MHz=min(v['achieved'] for v in proof['fmax'].values()),
   partial_target_pass=proof['partial_target_pass'],erasures=proof.get('erasures',False),
   original_count=len(originals),updated_T_rows=changed,allowed_pairs_count=len(pairs),
   raw_T_replacement=raw['stage_resources'],assignments=rows,allowed_pairs=pairs)
  if board=='20k':
   # R+H is a distinct shared-RS allocation; never use the simple stage sum.
   previous=read(ROOT/'reports/shared-sdf-evidence/updated-20k/summary.json')['old_shared_RS_B_replacement']['hybrid']
   case['R_H_replacement']={k:previous[k]-OLD[k]+resources[k] for k in KEYS}
   case['R_H_occupancy_percent']=occupancy(case['R_H_replacement'],board)
  cases.append(case)
 return dict(board=board,scope=__doc__,old_T_kernel_replaced=OLD,input_sha256=hashlib.sha256(oldpath.read_bytes()).hexdigest(),
  cases=cases,bandwidth_catalog=f'reports/control-only-{board}/bandwidth-catalog.json.gz',
  forward_information_and_bandwidth_unchanged=True,reverse_payload_allowed=False,
  formally_assigned_routes=0,adopted_receivers=0)

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 for b in CAPS:
  r=update(b);write_gzip(a.output/f'{b}-all-variants.json.gz',r)
  summary=copy.deepcopy(r)
  for c in summary['cases']:c.pop('assignments');c.pop('allowed_pairs')
  (a.output/f'{b}-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()

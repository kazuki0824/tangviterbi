"""Measured joint T/S K7 alternatives on R+H; unchanged CPU/link catalogues.

These retain inherited stage and integration allocations. Not whole P&R.
"""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
KEYS=('logic_sites_estimate','FF','BSRAM','DSP18')
CAP=dict(zip(KEYS,(20736,15552,46,48)))

def run():
 old=json.loads((ROOT/'reports/recovery-resource-audit.json').read_text())
 base={k:old['reconstructed'][k]-old['blocks']['T_K7'][k]-old['blocks']['S_BPSK_QPSK_K7_extra'][k] for k in KEYS}
 results=[]
 for f in sorted((ROOT/'reports/shared-k7-evidence').glob('*/summary.json')):
  p=json.loads(f.read_text())
  if 'logic_positions' not in p:continue
  kernel=dict(zip(KEYS,(p['logic_sites_with_ram_blockers'],p['FF_sites_with_ram_blockers'],p['BSRAM'],p['utilization']['MULT18X18']['used'])))
  whole={k:base[k]+kernel[k]for k in KEYS}
  results.append(dict(trial=f.parent.name,kernel=kernel,kernel_RAM16SDP4=p['RAM16SDP4'],R_H_replacement=whole,
    occupancy_percent={k:100*whole[k]/CAP[k]for k in KEYS},
    remaining={k:CAP[k]-whole[k]for k in KEYS},
    four_resource_allocation_pass=all(whole[k]<=CAP[k]for k in KEYS),
    kernel_target_pass=p['partial_target_pass'],fmax=p['fmax'],
    performance_pass=None,adopted=False))
 return dict(scope=__doc__,base_without_both_K7=base,cases=results,
    previous_independent_one_context_T_allocation=old['reconstructed'],
    baseline_scope_warning='old independent T kernel lacks three hierarchy contexts; new kernel has all four Viterbi contexts, not external depuncture/scheduler/FIFO',
    CPU_and_flows_unchanged=True,reverse_payload_allowed=False,
    ownership_catalog='reports/folded-t-evidence/budgets/20k-all-variants.json.gz',
    bandwidth_catalog='reports/control-only-20k/bandwidth-catalog.json.gz',
    route_pairs='reports/control-only-20k/raw-route-pairs.csv.gz',
    formally_assigned_routes=0,adopted_receivers=0)

if __name__=='__main__':print(json.dumps(run(),ensure_ascii=False,indent=2))

"""Replace the measured core and consume, rather than duplicate, integration reserve."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run():
 base=dict(logic=20472,FF_sites=13189,BSRAM=46,DSP18=34)
 old=dict(logic=5695,FF_sites=2681,BSRAM=4,DSP18=0)
 reserve=dict(logic=3000,FF_sites=2000,BSRAM=13,DSP18=0)
 cases=[]
 for f in sorted((ROOT/'reports/shared-k7-stream-evidence').glob('*/summary.json')):
  s=json.loads(f.read_text())
  new=dict(logic=s['logic_sites_with_ram_blockers'],FF_sites=s['FF_sites_with_ram_blockers'],BSRAM=s['BSRAM'],DSP18=s['utilization']['MULT18X18']['used'])
  delta={k:new[k]-old[k] for k in old}
  consumed={k:max(0,delta[k]) for k in old}
  left={k:max(0,reserve[k]-consumed[k]) for k in old}
  whole={k:base[k]+delta[k]-min(reserve[k],consumed[k]) for k in old}
  cases.append(dict(trial=f.parent.name,measured_core_plus_wrapper=new,delta_from_previous_core=delta,
   reserve_consumed=consumed,remaining_unimplemented_reserve=left,mixed_whole_budget=whole,
   Fmax=s['fmax'],partial_pass=s['partial_target_pass'],receiver_adopted=False))
 return dict(cases=cases,actual_whole_receiver_resources=None,
  warning='Same mixed whole budget means reserve was consumed, not that new logic is free. Delta compares two partial P&R mappings; remaining blocks still allocations. No new upstream T burst storage/controller counted as implemented.',
  upstream_storage_and_memory_timing_verified=False,CPU_and_boundary_flows_unchanged=True,formally_assigned_routes=0)
if __name__=='__main__':print(json.dumps(run(),indent=2))

"""Quantify 9K recovery targets; no unimplemented circuit is assigned a saving."""
from fractions import Fraction as F
from itertools import combinations
from pathlib import Path
import gzip,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def run():
 paths=['reports/four-soc-comparison/inputs.json.gz','reports/shared-sdf-evidence/9k-hybrid/summary.json','reports/folded-t-evidence/9k-baseline/summary.json']
 raw=[(ROOT/p).read_bytes() for p in paths]
 profiles=json.loads(gzip.decompress(raw[0]))['mode_profiles']
 def stage(identifier):
  r=next(r for r in profiles if r['id']==identifier)
  return next(p['FPGA_stage_estimates'] for p in r['profiles'] if not p['high'] and p['FPGA_MHz']==125 and p['RF_format']=='lossless20')
 t=stage('S3-T-000');s=stage('S3-S-000');fft=json.loads(raw[1]);k7=json.loads(raw[2]);keys=['logic_sites_estimate','FF','BSRAM','DSP18']
 u=fft['routed_utilization'];t['FFT']=dict(zip(keys,[sum(u[k]['used'] for k in ('LUT4','ALU')),u['DFF']['used'],u['BSRAM']['used'],u['MULT18X18']['used']]))
 t['trellis']=dict(zip(keys,[k7['logic_positions'],k7['FF'],k7['BSRAM'],0]))
 total={k:sum(v[k] for v in t.values()) for k in keys}
 cap=dict(zip(keys,[8640,6480,26,20]));gap=total[keys[0]]-cap[keys[0]]
 subset=[]
 for n in (1,2,3):
  for names in combinations(['trellis','FFT','RS'],n):
   old=sum(t[x]['logic_sites_estimate'] for x in names)
   subset.append(dict(blocks=list(names),current_mixed_logic=old,maximum_replacement_logic_before_missing_integration=old-gap,required_reduction=gap,
    rule='Subtract the still-unmeasured integration cost I from this ceiling; include three T contexts in replacement if trellis is replaced, otherwise in I. Not a lower bound or a proven achievable target.'))
 rate=F(26208)*1000000/F('1039.5')
 return dict(source_hashes={p:hashlib.sha256(r).hexdigest() for p,r in zip(paths,raw)},T_blocks=t,T_mixed_total=total,
  T_missing_integration_cost=None,T_capacity=cap,T_remaining_before_missing_integration={k:cap[k]-total[k] for k in keys},
  recovery_frontier=subset,
  T_clock_trials=[dict(clocks_per_step=c,arithmetic_minimum_MHz=float(c*rate/1000000),at_108MHz_arithmetic_percent=float(100*c*rate/108000000),implemented_three_context=False)for c in [2,4,5,6,8]],
  S_stage_only={k:sum(v[k]for v in s.values()) for k in keys},
  S_stage_missing=['BPSK/QPSK K7 full-mode implementation or measured trellis sharing','TMCC','physical memory, queues, CDC, I/O'],
  S_RF_high_CPU_before_driver_percent=93.42447916666667,
  FIR_migration_only_T_logic=total['logic_sites_estimate']-t['FIR']['logic_sites_estimate'],
  FIR_migration_high_CPU_before_driver_percent=123.435,
  two_images_combination='max(T,S), already applied; never subtract S from T again',
  new_9k_CAD_performed=False,adopted_receivers=0,formally_assigned_routes=0)
if __name__=='__main__':print(json.dumps(run(),indent=2))

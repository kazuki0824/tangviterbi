"""Reconcile full owner accounting against inherited U; conditional, not measured."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 paths=['reports/s3-owner-slice-tradeoff/results.json','reports/s3-owner-iteration-path/results.json']
 trade,iteration=[json.loads((ROOT/p).read_text()) for p in paths]
 rows=[]
 for size in (256,512):
  r=next(r for r in trade['rows'] if r['slice_pairs']==size)
  cases=[]
  for c in r['cases']:
   freq=c['assumed_owner_iterations_s'];old=c['core0_percent_by_management_cycles']['200']
   # Strip the whole inherited U0 and its differential scan placeholder.
   # Keep packing, fill, transfer API and explicit preparation-management reserve.
   fixed=old-20/2.4-1500*(freq-25000)/2.4e6
   budget=(100-fixed)*2.4e6/freq
   examples=[]
   for ex in iteration['rows']:
    scan=ex['cycles_at_alpha1_1']
    total=fixed+scan*freq/2.4e6
    differential=old+(scan-1500)*(freq-25000)/2.4e6
    assert abs(total-differential-(scan*25000-20e6)/2.4e6)<1e-10
    examples.append(dict(path=ex['case'],assumed_average_scan_cycles=scan,
      core0_percent_with_residual_zero=total,
      old_U_shortfall_Mcycles_s=(scan*25000-20e6)/1e6,
      residual_budget_Mcycles_s=(100-total)*2.4))
   cases.append(dict(samples=c['samples'],first=c['first'],frequency=freq,
       fixed_core0_percent=fixed,average_scan_budget_cycles_if_residual_zero=budget,examples=examples))
  rows.append(dict(slice_pairs=size,cases=cases,
    maximum_fixed_core0_percent=max(c['fixed_core0_percent'] for c in cases),
    maximum_average_scan_cycles_for_all_cases_residual_zero=min(c['average_scan_budget_cycles_if_residual_zero'] for c in cases),
    example_maxima={name:max(next(e['core0_percent_with_residual_zero'] for e in c['examples'] if e['path']==name) for c in cases) for name in ('collect_empty','collect_one_pending')}))
 result=dict(scope=__doc__,rows=rows,inherited_U_Mcycles_s=20,baseline_iterations_s=25000,
   maximum_baseline_scan_cycles_if_U_all_scan=800,
   assumptions=['alpha=1.1, API CPU20us, preparation management200cycles/iteration remain assumptions.',
    'Other residual cost is set to zero only for these scenarios; it is not known to be zero.',
    'Example path costs are substituted as average scan costs; actual state mixture remains unknown.',
    'Packing/fill/API/reserve boundaries still require full-path reconciliation. No feasibility proof.'],
   finalized=False,receiver_adopted=False,
   source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths+['experiments/s3_cost_reconciliation.py']})
 out=ROOT/'reports/s3-cost-reconciliation/results.json';out.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps([{k:v for k,v in r.items() if k!='cases'} for r in rows],indent=2))
if __name__=='__main__':main()

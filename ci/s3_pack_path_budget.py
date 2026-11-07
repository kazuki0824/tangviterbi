"""Map path counts to measured instruction sequences, leaving cycle costs unknown."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def report():
 root=ROOT/'reports/s3-pack-span';r=json.loads((root/'path-counts.json').read_text());linked=json.loads((root/'sdk-loop-summary.json').read_text());cost=linked['total_instructions_per_eight_samples'];rows=[]
 for row in r['rows']:
  for standard,cores in row['rates'].items():
   for worker,counts in enumerate(cores):
    steady=counts['blocks_s']*cost
    rows.append(dict(bank_samples=row['bank_samples'],first=row['first'],slice_pairs=row['slice_pairs'],standard=standard,worker=worker,linked_ideal_repetition_cycles_s=steady,remaining_of_240MHz_before_all_other_costs=240e6-steady,unmeasured_cycle_coefficients={k:counts[v] for k,v in [('run_setup','runs_s'),('slow_pair','slow_pairs_s'),('slice_excluding_clock_and_body','slices_s'),('clock_read','clock_reads_s')]},additionally_required=['RF poll/accept/collect, assigned by actual owner','SPI APIs and interrupts, assigned by actual owner','stalls and contention beyond ideal instruction count'],WCET_proven=False))
 return dict(scope=__doc__,input='path-counts.json',linked_instruction_evidence='sdk-loop-summary.json',repetition_instructions_per_block=cost,rows=rows)
if __name__=='__main__':
 r=report();(ROOT/'reports/s3-pack-span/path-budget.json').write_text(json.dumps(r,indent=2)+'\n');print('wrote',len(r['rows']),'worker scenarios')

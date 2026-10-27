"""Conditional S owner slice tradeoffs; averages and sensitivity, not elapsed bounds."""
import hashlib,json
from pathlib import Path
from ci.s3_pack_path_audit import run
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/s3-owner-slice-tradeoff'
def main():
 OUT.mkdir(exist_ok=True)
 coeff=json.loads((ROOT/'reports/s3-budgeted-fill/cfg-S/results.json').read_text())['coefficients']
 paths=run(6,[12288,12289,14288,14352],[64,128,256,512,1024])
 assert all(c['passed'] for c in paths['checks'])
 (OUT/'paths.json').write_text(json.dumps(paths,indent=2)+'\n')
 rows=[]
 for n in (64,128,256,512,1024):
  cases=[]
  for r in paths['rows']:
   if r['slice_pairs']!=n:continue
   rates=r['rates']['S']
   work=[sum(coeff[c]*v[k] for c,k in [('block','blocks_s'),('run','runs_s'),('slow_pair','slow_pairs_s'),('slice','slices_s')]) for v in rates]
   # Each owner iteration processes at most one nonempty packing slice.
   # This is a necessary average rate, not an achieved periodic schedule.
   frequency=max(1e6/30,rates[0]['slices_s'])
   scan_extra=1500*max(0,frequency-25000)/2.4e6
   base=1.1*(work[0]+15567*40e6/12288)/2.4e6+100e6*20e-6/16384*100+20/2.4
   cases.append(dict(samples=r['bank_samples'],first=r['first'],
    nonempty_owner_slices_s=rates[0]['slices_s'],assumed_owner_iterations_s=frequency,
    packing_only_mean_us_per_nonempty_slice=[work[w]*1.1/rates[w]['slices_s']/240 for w in (0,1)],
    scan_extra_percent=scan_extra,
    core0_percent_by_management_cycles={str(e):base+scan_extra+e*frequency/2.4e6 for e in (0,100,200,300)},
    core1_percent=(1.1*work[1]+10e6)/2.4e6))
  rows.append(dict(slice_pairs=n,cases=cases,
   core0_max_by_management_cycles={str(e):max(c['core0_percent_by_management_cycles'][str(e)] for c in cases) for e in (0,100,200,300)},
   core1_max=max(c['core1_percent'] for c in cases),
   mean_packing_slice_us_max=[max(c['packing_only_mean_us_per_nonempty_slice'][w] for c in cases) for w in (0,1)],
   owner_frequency_max=max(c['assumed_owner_iterations_s'] for c in cases)))
 result=dict(scope=__doc__,rows=rows,receiver_adopted=False,
  assumptions=dict(alpha=1.1,API_active_us=20,U_Mcycles_s=[20,10],baseline_owner_iterations_s=25000,extra_owner_iteration_cycles=1500,requested_scan_period_us=30,prepare_quantum_words=1024),
  limitations=['Mean nonempty slice time is not maximum per-call or owner response time.',
   'Owner frequency is max(33333.33, nonempty packing slice rate); empty polling may raise it.',
   '1500 cycles per extra iteration and management sensitivities are unmeasured; U is retained separately.',
   'No new claim about RF deadlines, publication latency, SPI gap, IRQ or bus contention.'],
  source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ('experiments/s3_owner_slice_tradeoff.py','ci/s3_pack_path_audit.py','experiments/s3_pack_path_probe.c','experiments/s3_parallel_pack.c','reports/s3-budgeted-fill/cfg-S/results.json')})
 (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 for r in rows:print({k:v for k,v in r.items() if k!='cases'})
if __name__=='__main__':main()

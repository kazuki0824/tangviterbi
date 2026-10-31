"""Real C path counts for unequal packing; conditional CPU model, not WCET."""
import json
from pathlib import Path
from ci.s3_pack_path_audit import run
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/s3-asymmetric-pack'
def main():
    coeff=json.loads((ROOT/'reports/s3-pack-span/cfg/results.json').read_text())['coefficients']
    result=[]
    for share in (8,7,6,5):
        evidence=run(share)
        evidence["core0_sixteenths"]=share
        assert all(c['passed'] for c in evidence['checks'])
        (OUT/f'paths-{share}.json').write_text(json.dumps(evidence,indent=2)+'\n')
        cases=[]
        for r in evidence['rows']:
            if r['slice_pairs']!=512:continue
            work=[]
            for rate in r['rates']['S']:
                work.append(sum(coeff[c]*rate[k] for c,k in
                    [('block','blocks_s'),('run','runs_s'),('slow_pair','slow_pairs_s'),('slice','slices_s')])/1e6)
            cycles=[1.1*(work[0]+21574*40/12288)+100*240*20/32768+20,1.1*work[1]+10]
            cases.append(dict(bank_samples=r['bank_samples'],first=r['first'],
                packing_Minstructions_s=work,planning_core_percent=[c/2.4 for c in cycles],
                average_packing_service_us_per_bank=[v*1.1*r['bank_samples']/40/240 for v in work]))
        # Both carry parities, all bank lengths in the declared steady range.
        slices=[0,0]
        for n in range(12288,14353):
            for carry in (0,1):
                pairs=(n+carry)//2;cut=pairs*share//16
                slices=[max(slices[0],(cut+511)//512),max(slices[1],(pairs-cut+511)//512)]
        result.append(dict(core0_sixteenths=share,cases=cases,
            planning_core_percent=[[min(r['planning_core_percent'][w] for r in cases),max(r['planning_core_percent'][w] for r in cases)] for w in (0,1)],
            max_slices_per_steady_bank=slices,receiver_adopted=False))
    out=dict(scope=__doc__,coefficients=coeff,rows=result,
        caveats=['Saved instruction coefficients are a model, not fresh target binary counts.',
        'Finite 64-bank cases; per-bank service is an average, not worst case or response time.',
        'Split setup and all current wrapper differences must fit U; target costs unmeasured.',
        'Changed worker slice bounds must be supplied to response analysis; prior equal-split bound is invalid.'])
    (OUT/'estimate.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps([dict(share=r['core0_sixteenths'],CPU=r['planning_core_percent'],slices=r['max_slices_per_steady_bank']) for r in result],indent=2))
if __name__=='__main__':main()

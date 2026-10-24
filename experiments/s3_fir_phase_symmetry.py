"""Exact symmetry screening of finite rational-FIR layouts; no quality/WCET claim."""
from fractions import Fraction as F
from math import gcd
from pathlib import Path
import argparse,json
ROOT=Path(__file__).resolve().parents[1]

def phase_rows(prototype,up):
    return [prototype[p::up] for p in range(up)]

def symmetric_dot(coeffs,samples):
    if len(coeffs)!=len(samples) or coeffs!=coeffs[::-1]:
        raise ValueError('requires one symmetric phase row and matching samples')
    n=len(coeffs)
    return sum(coeffs[k]*(samples[k]+samples[n-1-k]) for k in range(n//2))+(coeffs[n//2]*samples[n//2] if n%2 else 0)

def analyze(up,down,taps,delta,rate):
    if gcd(up,down)!=1:raise ValueError('reduced rational ratio required')
    n=up*taps+delta
    if n<up:raise ValueError('all phases must be populated')
    lengths=[(n-1-p)//up+1 for p in range(up)]
    mirror=[(n-1-p)%up for p in range(up)]
    self_phases=[p for p in range(up) if mirror[p]==p]
    multiplications=sum((lengths[p]+1)//2 if p in self_phases else lengths[p] for p in range(up))
    floor=rate*2*F(multiplications,up)/8
    return dict(up=up,down=down,nominal_taps_per_phase=taps,prototype_length=n,
        prototype_length_delta=delta,phase_length_min=min(lengths),phase_length_max=max(lengths),
        self_symmetric_phases=self_phases,phase_count=up,
        original_real_products_per_I_or_Q_per_phase_period=n,
        folded_real_products_per_I_or_Q_per_phase_period=multiplications,
        all_phase_symmetry_halves_MACs=False,
        ideal_MAC_only_Mcycles_s=float(floor),
        full_Q15_coeff_bytes=2*n,shared_prototype_Q15_coeff_bytes=2*((n+1)//2),
        assumptions=['Symmetric prototype; exact coefficient/sample arithmetic; no zero taps or other reuse exploited','Coefficient sharing across reverse phases saves storage, not products of distinct input windows','Pre-add, loads, extraction, phase addressing and output costs omitted','8 s16 products/issue and ideal 1 issue/cycle; pre-add width handling not priced','Delta +/-1 changes some row lengths, not a proven same-quality replacement'],
        receiver_adopted=False)

def report():
    budgets=json.loads((ROOT/'reports/s3-preprocess-break-even/fir-replacement-budget.json').read_text())
    rows=[];checks=[]
    for name,up,down,taps,rate,raw in [('T',32,63,32,F(512,63),16),('S',1443,2000,16,F(1443,50),40)]:
        b=next(x for x in budgets['rows'] if x['id']==f'S3-{name}-001')
        for delta in (-1,0,1):
            row=analyze(up,down,taps,delta,rate);row['standard']=name
            floor=row['ideal_MAC_only_Mcycles_s'];limits=b['replacement_FIR_including_unpack_must_be_below_Mcycles_s']
            row['remaining_Mcycles_s_low_high']=[x-floor for x in limits]
            row['MAC_only_excludes_beating_raw_low_high']=[floor>=x for x in limits]
            row['old_unpack_retained_excludes_beating_raw_low_high']=[floor+c*raw>=limits[k] for k,c in enumerate((3,5))]
            # A distinct CPU conversion pass must write 4 bytes/complex sample.
            # At most 16 bytes/store issue; deliberately omit all loads/decoding.
            store_floor=raw*4/16
            row['separate_Q15_unpack_store_only_Mcycles_s']=store_floor
            row['MAC_plus_separate_unpack_store_floor_Mcycles_s']=floor+store_floor
            row['separate_unpack_excludes_beating_raw_low_high']=[floor+store_floor>=x for x in limits]
            row['separate_unpack_scope']='CPU writes I16/Q16 intermediate arrays in a distinct pass, max 16 B/store issue, no fused FIR stores or hardware conversion'
            row['all_algorithms_excluded']=False
            rows.append(row)
            phases=[m*down%up for m in range(up)]
            checks.append(dict(name=f'{name}_{delta}_phase_permutation',passed=sorted(phases)==list(range(up))))
            n=row['prototype_length'];proto=[min(i,n-1-i)+1 for i in range(n)];pr=phase_rows(proto,up)
            checks.append(dict(name=f'{name}_{delta}_mirror_rows',passed=all(pr[p]==pr[(n-1-p)%up][::-1] for p in range(up))))
            checks.append(dict(name=f'{name}_{delta}_self_phase_count',passed=[p for p in range(up) if pr[p]==pr[p][::-1]]==row['self_symmetric_phases']))
    return dict(scope=__doc__,rows=rows,checks=checks,complete_preprocessing_comparison=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=report();a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({'checks':len(r['checks']),'failures':[x for x in r['checks'] if not x['passed']],'rows':[{k:v for k,v in x.items() if k in ('standard','prototype_length','self_symmetric_phases','ideal_MAC_only_Mcycles_s','remaining_Mcycles_s_low_high','shared_prototype_Q15_coeff_bytes')} for x in r['rows']]},indent=2))
    raise SystemExit(any(not c['passed'] for c in r['checks']))

"""Necessary break-even targets for replacing the inherited FIR cost, not WCET."""
import gzip,json,hashlib
from fractions import Fraction as F
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def report():
    previous=json.loads((ROOT/'reports/s3-preprocess-break-even/results.json').read_text())
    source=json.loads(gzip.decompress((ROOT/'reports/s3-partition-audit/inputs.json.gz').read_bytes()))
    out=[];checks=[]
    for ident,rate in [('S3-T-001',16),('S3-S-001',40)]:
        row=next(r for r in previous['rows'] if r['id']==ident)
        original=next(r for r in source['assignments'] if r['id']==ident)
        baseline=next(r for r in previous['rows'] if r['standard']==row['standard'] and not r['prefix'])
        kernel=original['stage_CPU_models']['FIR']['known_model_Mcycles_per_s']
        limit=[kernel[k]-row['net_increase_vs_raw_Mcycles_s'][k] for k in range(2)]
        # Exact inherited sample rates independently reconstructed from output type.
        ratio=F(32,63) if rate==16 else F(1443,2000)
        output=rate*float(ratio)
        checks.append(dict(name=ident+'_sample_rate',passed=abs(output*4-row['forward_MBps'])<1e-10))
        for k in range(2):
            fixed=row['CPU_before_link_Mcycles_s'][k]-kernel[k]
            checks.append(dict(name=ident+'_break_even_'+str(k),passed=abs(fixed+limit[k]+row['API_Mcycles_s']-baseline['CPU_before_link_Mcycles_s'][k]-baseline['API_Mcycles_s'])<1e-9))
        out.append(dict(id=ident,old_FIR_including_unpack_Mcycles_s=kernel,
            replacement_FIR_including_unpack_must_be_below_Mcycles_s=limit,
            required_speedup_greater_than=[kernel[k]/limit[k] for k in range(2)],
            aggregate_cycles_per_input_complex_sample_limit=[v/rate for v in limit],
            aggregate_cycles_per_output_complex_sample_limit=[v/output for v in limit],
            output_complex_Msample_s=output,output_input_ratio=str(ratio),
            lower_bound_proves_impossible=False,implementation_meets_target=False))
    return dict(scope=__doc__,assumptions=['All non-FIR prelink costs, output Q15 format and API costs fixed','FIR cost includes raw IQ unpack; packing is not added again','Limits compare same inherited low/high scenarios, not measured bounds','Equality only ties raw; improvement needs strict inequality','A fused implementation changing fixed costs requires full recomputation'],rows=out,checks=checks)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=report();a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
    raise SystemExit(any(not c['passed'] for c in r['checks']))

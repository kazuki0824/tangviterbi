"""Logical operation counts of the streaming reference; not CPU WCET or bus rates."""
import json
from fractions import Fraction as F
from pathlib import Path

def report():
    rows=[];checks=[]
    for name,rate,up,down,k in [('T',16,32,63,32),('S',40,1443,2000,16)]:
        output=F(rate*up,down); old=2*k*output; new=2*rate
        rows.append(dict(standard=name,input_complex_Msample_s=rate,output_complex_Msample_s=float(output),
            previous_signed10_decodes_M_s=float(old),stream_signed10_decodes_M_s=new,
            decode_reduction_factor=float(old/new),raw_reads_MB_s=4*rate,
            history_writes_MB_s=4*rate,history_reads_MB_s=float(4*k*output),
            coefficient_reads_MB_s=float(2*k*output),real_MAC_M_s=float(2*k*output),
            minimum_live_history_bytes=4*k,reference_state_bytes=156,
            coefficient_table_bytes=2*k*up,accumulator_abs_bound=k*512*32768,
            scalar_one_MAC_per_cycle_two_core_utilization_percent=float(2*k*output/480*100),
            target_cycles_measured=False,performance_qualified=False))
        # Count scheduling and logical reuse over exactly one down-input period.
        times=[m*down//up for m in range(up)]
        checks.append(dict(name=name+'_schedule',passed=len(set(times))==up and max(times)<down))
        checks.append(dict(name=name+'_decode_ratio',passed=old/new==F(k*up,down)))
        checks.append(dict(name=name+'_int32_bound',passed=k*512*32768<2**31))
    return dict(scope=__doc__,rows=rows,checks=checks,
        limitations=['No claim of register residency: C arrays may be loaded/stored on every tap',
        'Output rounding/saturation and receiver quality are outside this reference',
        'Counts are logical C accesses; compiler/register/cache effects not physical traffic',
        'No new communication route or performance-qualified partition is established'])
if __name__=='__main__':
    r=report();p=Path(__file__).resolve().parents[1]/'reports/s3-preprocess-break-even/stream-reference-budget.json'
    p.write_text(json.dumps(r,indent=2)+'\n')
    print(f"{len(r['checks'])} checks; failures: {sum(not c['passed'] for c in r['checks'])}")
    raise SystemExit(any(not c['passed'] for c in r['checks']))

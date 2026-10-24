"""Conditional ownership audit, not measured CPU/WCET or an adopted receiver."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def report():
    rows = []
    checks = []
    old = json.loads((ROOT/'reports/s3-batch-bank-closure/results.json').read_text())
    for standard, rate, aggregate, forward in [('T',16,F('185.375'),F('40.01')),('S',40,F('448.4375'),F('100.01'))]:
        # Explicit decomposition hypothesis, NOT a recovered WCET breakdown.
        packing = rate * 8
        residual = aggregate - packing
        api = forward * 240 * 20 / 32768
        serial = residual + api
        lo = max(F(0), 1-(240-serial)/packing)
        hi = min(F(1), F(240,packing))
        equal = [serial+packing/2, F(packing,2)]
        balanced = (packing+serial)/(2*packing)
        row = dict(standard=standard,rate_Msample_s=rate,payload_MB_s=rate*2.5,
            packing_cycles_per_sample_assumed=8,packing_Mcycles_s=packing,
            residual_charged_to_coordinator_Mcycles_s=float(residual),
            API_Mcycles_s=float(api),equal_packing_core_percent=[float(x/240*100) for x in equal],
            worker1_fraction_open_interval=[float(lo),float(hi)],
            balanced_worker1_fraction=float(balanced),
            balanced_core_percent=float((aggregate+api)/480*100),
            balanced_extra_budget_cycles_s_per_core=float((480-aggregate-api)*1e6/2),
            measured=False,receiver_adopted=False)
        prev=next(r for r in old['cpu_cases'] if r['standard']==standard and r['batch']==32768)
        checks.append(dict(name=standard+'_aggregate_reconciles',passed=abs(sum(equal)-F(str(prev['RF_high_Mcycles_s']))-F(str(prev['API_Mcycles_s'])))<F(1,10**8)))
        checks.append(dict(name=standard+'_balanced_conserves',passed=serial+packing*(1-balanced)==packing*balanced))
        checks.append(dict(name=standard+'_interval_nonempty',passed=lo<hi))
        rows.append(row)
    paths=['experiments/s3_parallel_pack.c','experiments/s3_native_capture.c','reports/s3-batch-bank-closure/results.json']
    return dict(scope=__doc__,assumptions=['8 cycles/sample packing sensitivity; not target WCET','Historical aggregate minus assumed packing is an unclassified residual, assigned entirely to coordinator for this scenario','Both SPI APIs on coordinator; 20 us active per 32768 bytes','No measured common-clock, IRQ, RTOS or memory contention bound','Open share intervals require strictly less than 100 percent; finite-bank rounding excluded'],rows=rows,checks=checks,source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},complete_estimate=False)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=report();a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({'checks':len(r['checks']),'failures':[x for x in r['checks'] if not x['passed']],'rows':r['rows']},indent=2))
    raise SystemExit(any(not x['passed'] for x in r['checks']))

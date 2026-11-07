"""Exhaustive scan phase within specified finite timing scenarios, not all RF traces."""
import json,hashlib
from pathlib import Path
from experiments.s3_short_transfer import simulate
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/s3-short-transfer-audit'
def main():
    OUT.mkdir(exist_ok=True)
    prior=json.loads((ROOT/'reports/s3-short-transfer/schedule.json').read_text())['rows']
    by={(r['chunk_bytes'],r['publication_us'],r['scan_us'],r['pattern']):r for r in prior}
    pairs=[]
    for key,a in by.items():
        if key[0]!=32768:continue
        b=by[(16384,*key[1:])]
        pairs.append(dict(publication_us=key[1],scan_us=key[2],pattern=key[3],
            old_peak=a['peak_reserved_unretired_bytes'],new_peak=b['peak_reserved_unretired_bytes'],
            reduction_bytes=a['peak_reserved_unretired_bytes']-b['peak_reserved_unretired_bytes'],
            new_capacity_pass=b['first_capacity_failure'] is None))
    phases=[]
    for chunk,scan in ((32768,40),(16384,40),(16384,30)):
        for name,pattern in [('nominal',[12288]),('maximum',[14352]),('alternating',[12289,14352])]:
            minimum=None;best=None;failures=0;worst_phase=None;first=None
            for phase in range(scan*240):
                r=simulate(chunk,320,scan,(pattern*128)[:128],scan_phase_cycles=phase)
                spare=r['free_bytes_at_peak']
                if minimum is None or spare<minimum:
                    minimum=spare;worst_phase=phase;first=r['first_capacity_failure']
                best=spare if best is None else max(best,spare)
                failures+=r['first_capacity_failure'] is not None
            item=dict(chunk_bytes=chunk,publication_us=320,scan_us=scan,pattern=name,banks=128,
                checked_phases=scan*240,failing_phases=failures,worst_free_bytes=minimum,best_free_bytes=best,
                worst_phase_cycles=worst_phase,first_failure_at_worst_phase=first)
            phases.append(item);print(item,flush=True)
    result=dict(scope=__doc__,pairs=pairs,phase_sweep=phases,receiver_adopted=False,
        limitations=['All integer 240MHz-cycle phases within each declared scan period only.',
        'Only the three specified 128-bank sequences; publication latency is fixed to 320us.',
        'Synthetic scheduling model, no measured CPU times, DMA contention or FPGA memory behavior.'],
        source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ('experiments/s3_short_transfer.py','experiments/s3_short_transfer_audit.py')})
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()

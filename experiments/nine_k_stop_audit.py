"""Screen existing components optimistically; not an integrated resource bound."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def audit():
    sources = {}
    def read(name):
        p = ROOT / name
        sources[name] = hashlib.sha256(p.read_bytes()).hexdigest()
        return json.loads(p.read_text())
    frontier = read('reports/9k-recovery-frontier.json')
    k7 = read('reports/three-context-k7-split/summary.json')
    other = sum(v['logic_sites_estimate'] for k,v in frontier['T_blocks'].items()
                if k not in ('FFT','trellis','RS'))
    rows = []
    for fft_name in ('hybrid','resident'):
        fft = read(f'reports/shared-sdf-evidence/9k-{fft_name}/summary.json')
        for rs_name in ('resetless','resetless4','shared-resetless4'):
            rs = read(f'reports/s3-area/{rs_name}.json')
            total = other + k7['logic_positions'] + fft['routed_logic_positions'] + rs['RS']['logic_equivalents']
            rows.append(dict(FFT=fft_name,RS=rs_name,
                optimistic_mixed_logic=total,excess_before_missing_cost=total-8640,
                K7_actual_MHz=next(iter(k7['fmax'].values()))['achieved'],
                K7_required_MHz=4*(4992*6*7/8)/1039.5,
                admission=False))
    assert other == 1712
    assert all(r['excess_before_missing_cost'] > 0 for r in rows)
    return dict(rows=rows,source_sha256=sources,
        qualification='Optimistic screen mixes independent logic equivalents and routed sites; NOT a silicon lower bound. K7 RAM blockers and integration omitted. Every row also fails measured K7 timing.',
        validated_replacement_candidates=0,status='pause_9k_implementation_search',
        mathematical_impossibility_proven=False)

if __name__ == '__main__':
    print(json.dumps(audit(),indent=2))

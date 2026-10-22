"""Join recorded measurements; never promote a partial core to a receiver."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    rows = []
    inputs = []
    for name, fft in [('refresh-predecode', False), ('fft', True),
                      ('fft-refresh', True), ('fft-metadata-refresh', True), ('fft-beat-hold', True)]:
        path = ROOT / f'reports/shared-receiver-{name}-evidence/summary.json'
        data = json.loads(path.read_text())
        inputs.append(path)
        for source, digest in data['source_sha256'].items():
            assert hashlib.sha256((ROOT/source).read_bytes()).hexdigest() == digest, source
        cost = data.get('logic_with_ram_blockers')
        mix = None
        if cost is not None:
            # Replace each prior allocated/measured block exactly once.
            mix = dict(logic=19891-3854-7468-(2729 if fft else 0)+cost,
                       FF=11759-1481-3528-(1502 if fft else 0)+data['FF_sites_with_ram_blockers'],
                       BSRAM=43-5-(10 if fft else 0)+data['BSRAM'],
                       DSP18=34-2-(4 if fft else 0)+data['DSP18'])
        rows.append(dict(name=name, actual_FFT=fft, measured_partial={
            key: data.get(key) for key in ('pnr_exit', 'route_completed', 'partial_target_pass',
                                          'logic_with_ram_blockers', 'FF_sites_with_ram_blockers',
                                          'BSRAM', 'DSP18', 'fmax')},
            mixed_diagnostic=mix, remaining_stages_are_allocations=True, adopted=False))
    dependencies = ['rtl/shared_sdf_fft.sv',
                    'reports/pr7-fft-archive/rtl/research_sdf_quarter_q16.hex',
                    'reports/pr7-fft-archive/experiments/research_sdf_oracle.py',
                    'tests/test_shared_sdf_fft.py', 'tests/test_sdf_delay_cache.py',
                    'tests/test_common_clock_sdram.py']
    result = dict(scope=__doc__, variants=rows, whole_receiver_verified=False,
                  formal_routes=0, adopted_receivers=0, scenario1_resumed=False,
                  resource_overlay_is_not_a_lower_bound=True,
                  extra_software_decimation_or_requantization=False,
                  external_IO_STA_verified=False, S3_WCET_verified=False,
                  evidence_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in inputs},
                  supplemental_source_sha256={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
                                              for p in dependencies})
    (ROOT/'reports/continuation-20261020.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()

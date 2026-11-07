#!/usr/bin/env python3
"""Recount recovered FPGA netlists; this is not a circuit or timing test."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

RELATIVE_ROOT = Path('reports/s3-t-preprocess-integration/quality-fpga')
# Original gzip SHA256 values retained in the pre-interruption staged manifest.
EXPECTED = {
    'baseline-fifo/core-mapped.json.gz': 'dbe7a05da776e064436c8e99fac100d75d9e82e4416079a39b1fecb6c5a509a7',
    'baseline-fifo/probe-mapped.json.gz': '8e591ffddff39b82509420d40ace9151b695968ffbe03c59b8664363d3065160',
    'baseline-fifo/routed.json.gz': 'c0def2bc6dd8aa553cb74d551f161aac1016b3ba30b3812760538a5252fcc532',
    'residual-fifo/core-mapped.json.gz': 'c6ed889f690ebd1a3df464a0bb27d546d375acf144a845dfa310805d74abfb98',
    'residual-fifo/probe-mapped.json.gz': '2aefeef630138b6508ce39fb83b1ed6dfa4621465058959744a011979c8c4539',
    'residual-fifo/routed.json.gz': 'a7c1863d0a2949d63f19a99d397661f953bd350b95e31ae127c6f94c642582bf',
}
# These are the BSRAM primitive variants present in the six pinned netlists.
BSRAM_TYPES = ('SPX9', 'SDPX9B', 'SP', 'SDP')


def flag(value):
    try:
        return int(str(value or 0), 2) != 0
    except ValueError:
        return bool(value)


def recount(repo):
    rows = []
    for relative, expected_sha in EXPECTED.items():
        path = RELATIVE_ROOT / relative
        row = {'path': path.as_posix(), 'expected_gzip_sha256': expected_sha}
        rows.append(row)
        try:
            data = (repo / path).read_bytes()
        except FileNotFoundError:
            row['status'] = 'MISSING'
            continue
        except OSError as exc:
            row.update(status='READ_ERROR', error=str(exc))
            continue
        actual_sha = hashlib.sha256(data).hexdigest()
        row.update(bytes=len(data), gzip_sha256=actual_sha,
                   original_manifest_sha256_match=actual_sha == expected_sha)
        if actual_sha != expected_sha:
            row['status'] = 'HASH_MISMATCH'
            continue
        try:
            decoded = gzip.decompress(data)
            netlist = json.loads(decoded)
            tops = [(name, module) for name, module in netlist['modules'].items()
                    if not flag(module.get('attributes', {}).get('blackbox'))]
        except (OSError, EOFError, ValueError, KeyError, TypeError) as exc:
            row.update(status='PARSE_ERROR', error=str(exc))
            continue
        row['decoded_sha256'] = hashlib.sha256(decoded).hexdigest()
        row['creator'] = netlist.get('creator')
        if len(tops) != 1:
            row.update(status='TOP_COUNT_ERROR', non_blackbox_modules=[name for name, _ in tops])
            continue
        name, module = tops[0]
        cells = module.get('cells', {})
        counts = Counter(cell['type'] for cell in cells.values())
        dsp = counts['MULT18X18']
        bsram = sum(counts[t] for t in BSRAM_TYPES)
        expected_bsram = 2 if relative.startswith('baseline-fifo/') else 3
        row.update(
            top_module=name,
            cell_count=len(cells),
            primitive_counts=dict(sorted(counts.items())),
            MULT18X18_cells=dsp,
            BSRAM_cells=bsram,
            explicit_DFF_cells=sum(v for t, v in counts.items() if t.startswith('DFF')),
            explicit_LUT1_to_LUT4_cells=sum(counts[t] for t in ('LUT1', 'LUT2', 'LUT3', 'LUT4')),
            ALU_cells=counts['ALU'],
            RAM16SDP4_cells=counts['RAM16SDP4'],
            expected_resource_counts={'MULT18X18': 4, 'BSRAM': expected_bsram},
            resource_counts_match=(dsp == 4 and bsram == expected_bsram),
        )
        if relative.endswith('/routed.json.gz'):
            dsp_bels = [c.get('attributes', {}).get('NEXTPNR_BEL')
                        for c in cells.values() if c['type'] == 'MULT18X18']
            bsram_bels = [c.get('attributes', {}).get('NEXTPNR_BEL')
                          for c in cells.values() if c['type'] in BSRAM_TYPES]
            distinct = (None not in dsp_bels + bsram_bels and
                        len(set(dsp_bels)) == dsp and len(set(bsram_bels)) == bsram)
            row.update(DSP_BELs=dsp_bels, BSRAM_BELs=bsram_bels,
                       all_DSP_and_BSRAM_BELs_distinct=distinct)
            row['resource_counts_match'] = row['resource_counts_match'] and distinct
        row['status'] = 'VERIFIED' if row['resource_counts_match'] else 'RESOURCE_COUNT_MISMATCH'
    states = Counter(row['status'] for row in rows)
    by_path = {row['path']: row for row in rows}
    comparisons = []
    for stage in ('core-mapped.json.gz', 'probe-mapped.json.gz', 'routed.json.gz'):
        baseline = by_path[(RELATIVE_ROOT / 'baseline-fifo' / stage).as_posix()]
        residual = by_path[(RELATIVE_ROOT / 'residual-fifo' / stage).as_posix()]
        if baseline['status'] == residual['status'] == 'VERIFIED':
            comparisons.append({
                'stage': stage,
                'baseline_MULT18X18': baseline['MULT18X18_cells'],
                'residual_MULT18X18': residual['MULT18X18_cells'],
                'MULT18X18_delta': residual['MULT18X18_cells'] - baseline['MULT18X18_cells'],
                'baseline_BSRAM': baseline['BSRAM_cells'],
                'residual_BSRAM': residual['BSRAM_cells'],
                'BSRAM_delta': residual['BSRAM_cells'] - baseline['BSRAM_cells'],
            })
    return {
        'verification_kind': 'fresh_read_only_recount_of_recovered_original_netlists',
        'audit_status': 'SOURCE_AND_COUNTS_VERIFIED' if states['VERIFIED'] == len(EXPECTED) else 'INCOMPLETE',
        'non_fail_fast': True,
        'method': 'Verify original gzip SHA256; count only cells in the single non-blackbox top module; inspect distinct MULT18X18 and BSRAM BELs in routed files.',
        'status_counts': dict(sorted(states.items())),
        'records': rows,
        'comparisons': comparisons,
        'scope_limitations': [
            'This is a fresh recount of preserved JSON, not recovery of the missing original summary.json or its audit.',
            'No RTL simulation, circuit rebuild, streaming deadline or FIFO-overrun check was executed.',
            'No timing, Fmax, STA coverage or hardware performance conclusion is established by these counts.',
            'No signal-quality equivalence or full receiver adoption conclusion is established.',
            'Explicit LUT/ALU/DFF primitive counts exclude any additional RAM16SDP4 architecture footprint; total logic/FF positions are not asserted.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = recount(args.repo)
    text = json.dumps(result, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end='')
    return 0 if result['audit_status'] == 'SOURCE_AND_COUNTS_VERIFIED' else 1


if __name__ == '__main__':
    raise SystemExit(main())

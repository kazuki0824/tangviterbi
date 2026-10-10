#!/usr/bin/env python3
"""Persist compact reproducible communication evidence, including failed trials."""
from pathlib import Path
import hashlib
import json
import shutil
import argparse
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--test-log', type=Path)
args = parser.parse_args()
target = ROOT/'reports/s3-communication-evidence'
target.mkdir(parents=True, exist_ok=True)
tests = {}
for name in ('s3-page-reorder', 's3-rx-page-store', 's3-spi-iq-tx',
             's3-spi-rx', 's3-spi-rx-faults', 's3-spi-page-pipeline'):
    p = ROOT/'build'/name/'result.json'
    tests[name] = json.loads(p.read_text())
tests['s3-page-guard'] = (ROOT/'build/s3-page-guard/result.txt').read_text().strip()
history = []
for p in sorted((ROOT/'build/s3-comm-endpoint/trials').glob('*/result.json')):
    r = json.loads(p.read_text())
    history.append({k: r.get(k) for k in ('sources', 'exit_code', 'fmax', 'utilization', 'warnings', 'pnr_trials')})
sources = sorted(set(ROOT.glob('rtl/s3_*.sv')) | set(ROOT.glob('tests/test_s3_*page*.py')) |
                 set(ROOT.glob('tests/test_s3_spi*.py')) | set(ROOT.glob('ci/s3_comm*.py')))
record = dict(tests=tests, prior_endpoint_trials=history, receiver_adopted=False,
              source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
record['tools'] = {tool: subprocess.run([tool, '--version'], text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, check=True).stdout.strip()
                   for tool in ('yosys', 'nextpnr-himbaechel')}
record['pin_constraints_sha256'] = hashlib.sha256((ROOT/'experiments/s3_spi_rx_benchmark.cst').read_bytes()).hexdigest()
if args.test_log:
    text = args.test_log.read_text()
    if not text.rstrip().endswith('OK'):
        raise ValueError('test log is incomplete or failed; do not record it as passing')
    record['full_test_log_sha256'] = hashlib.sha256(args.test_log.read_bytes()).hexdigest()
    shutil.copy2(args.test_log, target/'unittest.log')
(target/'results.json').write_text(json.dumps(record, indent=2)+'\n')
for name, source in (
    ('endpoint-pnr.log', 'build/s3-comm-endpoint/pnr.log'),
    ('tc8psk-metric-pnr.log', 'build/s3-fec-extensions/tc8psk-metric/fec-mem/pnr.log')):
    shutil.copy2(ROOT/source, target/name)
print(target)

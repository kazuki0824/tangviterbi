"""Run every selected transport check without fail-fast; preserve evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'reports/s3-bulk-transport'
MODULES = [
 'test_s3_bulk_transport', 'test_s3_bulk_page_pipeline',
 'test_s3_spi_rx', 'test_s3_spi_rx_faults', 'test_s3_spi_page_pipeline',
 'test_s3_transport', 'test_s3_control', 'test_s3_rf_pump',
 'test_s3_fft_exchange', 'test_s3_batch_bank_closure',
]

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cases=[]; logs=[]
    for name in MODULES:
        command=[sys.executable,'-m','unittest','discover','-s','tests','-p',name+'.py','-v']
        try:
            run=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=180)
            ok=run.returncode==0; log=run.stdout+run.stderr
        except (OSError,subprocess.TimeoutExpired) as exc:
            ok=False; log=str(exc)
        cases.append(dict(module=name,ok=ok))
        logs.append(name+'\n'+log+'\n')
        print(name, 'OK' if ok else 'NG', flush=True)
    diff=subprocess.run(['git','diff','--check'],cwd=ROOT,text=True,capture_output=True)
    cases.append(dict(module='git_diff_check',ok=diff.returncode==0))
    logs.append('git diff --check\n'+diff.stdout+diff.stderr)
    files=['experiments/s3_spi_transport.c','experiments/s3_spi_transport.h',
           'rtl/s3_spi_rx.sv','rtl/s3_bulk_page_split.sv','tests/s3_bulk_transport_host.c',
           'tests/test_s3_bulk_transport.py','tests/test_s3_bulk_page_pipeline.py',
           'experiments/check_s3_bulk_transport.py']
    result=dict(checks=cases,all_pass=all(x['ok'] for x in cases),
        source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},
        scope='C SDK shim and RTL functional simulation; no hardware WCET, SDK link, P&R or RF-to-TS',
        formal_routes=0,receiver_adopted=False)
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    (OUT/'tests.log').write_text('\n'.join(logs))
    return 0 if result['all_pass'] else 1

if __name__=='__main__':sys.exit(main())

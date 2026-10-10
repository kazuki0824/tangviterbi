#!/usr/bin/env python3
"""Freeze memory/IQ evidence; refuse stale source hashes or failed test logs."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--test-log',type=Path)
a=p.parse_args()
out=ROOT/'reports/s3-psram-evidence';out.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record=dict(receiver_adopted=False,hardware_verified=False,physical_timing_proven=False,
            implementation_complete=False,synthesis={},tests={},prior_trials={},
            routed_logic_positions={},resource_accounting='Post-route LUT4 + ALU; pre-placement LUT4 contains ALU blockers and is not directly comparable')
for name in ('s3-psram','s3-memory-bridge','s3-memory-fec','s3-comm-pingpong'):
    report=json.loads((ROOT/f'reports/{name}.json').read_text())
    for source,digest in report['sources'].items():
        if sha(ROOT/source)!=digest:raise ValueError('stale synthesis: '+source)
    record['synthesis'][name]=report
    if report.get('utilization'):
        u=report['utilization'];sites=u['LUT4']['used']+u['ALU']['used']
        record['routed_logic_positions'][name]=dict(used=sites,available=8640,percent=sites*100/8640)
    build=ROOT/'build'/(name if name=='s3-comm-pingpong' else name+'-pnr')
    shutil.copy2(build/'pnr.log',out/f'{name}-pnr.log')
    record['prior_trials'][name]=[json.loads(f.read_text()) for f in sorted((build/'trials').glob('*/result.json'))]
    for trial in sorted((build/'trials').glob('*')):
        for filename in ('pnr.log','status.txt'):
            if (trial/filename).exists():
                target=out/'prior-trials'/name/trial.name/filename
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(trial/filename,target)
    if name=='s3-memory-fec':
        for f in ('viterbi.sv','rs.sv'):shutil.copy2(build/f,out/f'combined-{f}')
for name,path in (
    ('buffered_memory','s3-psram/payload/result.json'),
    ('DDR_pins','s3-psram/ddr-results.json'),
    ('SPI_to_DDR','s3-psram-pipeline/result.json'),
    ('IQ_cadence','s3-iq-pingpong/result.json')):
    record['tests'][name]=json.loads((ROOT/'build'/path).read_text())
for name,path in (
    ('bounded_memory_faults','s3-psram/faults/simulation.log'),
    ('ack_deadline','s3-rx-page-store/ack-timeout/simulation.log'),
    ('independent_IQ_timeout','s3-iq-pingpong/timeout/simulation.log')):
    text=(ROOT/'build'/path).read_text()
    if 'PASS' not in text or 'FATAL' in text:raise ValueError('test not passing: '+path)
    record['tests'][name]=text.strip()
wire=record['tests']['SPI_to_DDR']
elapsed=float(re.search(r'elapsed_ns=([0-9.]+)',wire['output'])[1])
mbps=wire['payload_bytes']*1000/elapsed
record['conditional_bandwidth']=dict(
    burst_bytes=256,write_command_cycles=82,read_command_cycles=87,core_MHz=99,
    isolated_write_MBps=256*99/82,isolated_read_MBps=256*99/87,
    equal_read_write_aggregate_MBps=512*99/(82+87),
    SPI_to_DDR_to_output_MBps=mbps,margin_over_S_native_100_MBps=mbps-100,
    scope='functional model and sequential RF ring only; no CPU/API/control cost, real IO or interleaver traffic included')
sources=set(ROOT.glob('rtl/s3_*.sv'))|set(ROOT.glob('tests/test_s3_psram*.py'))|set(ROOT.glob('tests/test_s3_spi_iq_pingpong.py'))|set(ROOT.glob('tests/fixtures/*ddr*.sv'))|set(ROOT.glob('tests/fixtures/w955*.sv'))|set(ROOT.glob('ci/s3_psram*.py'))
record['source_sha256']={str(f.relative_to(ROOT)):sha(f) for f in sorted(sources)}
record['tools']={t:subprocess.run([t,'--version'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,check=True).stdout.strip() for t in ('yosys','nextpnr-himbaechel')}
if a.test_log:
    text=a.test_log.read_text()
    if not text.rstrip().endswith('OK'):raise ValueError('test log incomplete or failed')
    record['unittest_log_sha256']=sha(a.test_log)
    shutil.copy2(a.test_log,out/'unittest.log')
fs=ROOT/'build/s3-psram-pnr/psram-bist.fs'
if fs.exists():
    # A locally generated memory BIST image, never a T/S receiver image.
    data=fs.read_bytes();(out/'psram-bist.fs.gz').write_bytes(gzip.compress(data,mtime=0))
    record['BIST_bitstream']=dict(fs_bytes=len(data),sha256=sha(fs),
        routed_json_sha256=sha(ROOT/'build/s3-psram-pnr/routed.json'),
        compressed_sha256=sha(out/'psram-bist.fs.gz'),receiver_image=False,safe_to_flash=False,
        unproven=['DQ/RWDS sampling eye','external and phase-related IO timing','real hardware operation'])
(out/'results.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record['conditional_bandwidth'],indent=2))

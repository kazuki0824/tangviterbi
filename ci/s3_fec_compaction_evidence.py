#!/usr/bin/env python3
"""Preserve successful/failed compaction evidence; reject stale synthesis."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ci'))
from s3_logic_site_audit import audit
p=argparse.ArgumentParser();p.add_argument('--test-log',type=Path,required=True);a=p.parse_args()
out=ROOT/'reports/s3-fec-compaction-evidence';out.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
log=a.test_log.read_text()
if not log.rstrip().endswith('OK'):raise ValueError('incomplete or failed tests')
shutil.copy2(a.test_log,out/'unittest.log')
r=dict(receiver_adopted=False,safe_to_flash=False,profiles={},tests={},source_sha256={},
       scope='FEC arithmetic/storage and mapped area investigation, not a receiver')
audits={}
for name in ('s3-psram','s3-memory-bridge','s3-memory-fec',
    's3-memory-fec-compact','s3-memory-fec-compact-b1','s3-memory-fec-compact-b1-rs',
    's3-memory-fec-compact-b1-rs-acs22','s3-memory-fec-compact-b1-rs-acs22-q15',
    's3-memory-fec-compact-b1-rs-acs22-q15-folded'):
    report=json.loads((ROOT/f'reports/{name}.json').read_text());build=ROOT/f'build/{name}-pnr'
    for source,digest in report['sources'].items():
        if sha(ROOT/source)!=digest:raise ValueError('stale synthesis: '+source)
    result=audit(build/'packed.json')
    if report.get('logic_site_audit') and result!=report['logic_site_audit']:
        raise ValueError('audit differs: '+name)
    if report.get('utilization'):
        u=report['utilization'];sites=u['LUT4']['used']+u['ALU']['used']
        assert result['minimum_required_logic_sites']<=sites
        result['actual_routed_logic_sites']=sites
        result['actual_routed_logic_site_percent']=sites*100/8640
    audits[name]=result
    r['profiles'][name]=dict(report=report,audit=result)
    target=out/name;target.mkdir(exist_ok=True)
    for filename in ('viterbi.sv','rs.sv','top.sv','synth.ys','clocks.py','pins.cst','pnr.log','pack-only.log'):
        if (build/filename).exists():shutil.copy2(build/filename,target/filename)
    r['profiles'][name]['prior_trials']=[]
    for trial in sorted((build/'trials').glob('*')):
        if (trial/'result.json').exists():
            r['profiles'][name]['prior_trials'].append(json.loads((trial/'result.json').read_text()))
        for f in ('pnr.log','status.txt'):
            if (trial/f).exists():
                d=target/'prior-trials'/trial.name;d.mkdir(parents=True,exist_ok=True);shutil.copy2(trial/f,d/f)
for name,path in (
    ('ACS_arbitrary','s3-tc8psk-arithmetic-arbitrary/result.json'),
    ('ACS_Q15','s3-tc8psk-arithmetic-q15/result.json'),
    ('RS_independent','s3-rs-compact/vectors.json'),
    ('metric_chain','s3-tc8psk-metric-folded-chain/result.json')):
    r['tests'][name]=json.loads((ROOT/'build'/path).read_text())
for name,path in (
    ('cycle_equivalence','s3-tc8psk-equivalence/simulation.log'),
    ('arbitrary_ACS','s3-tc8psk-arithmetic-arbitrary/simulation.log'),
    ('Q15_ACS','s3-tc8psk-arithmetic-q15/simulation.log'),
    ('RS_failure_paths','s3-rs-compact-failures/simulation.log')):
    s=(ROOT/'build'/path).read_text()
    if 'PASS' not in s or 'FATAL' in s:raise ValueError('failed test: '+path)
    r['tests'][name]=s.strip()
# Preserve all standalone timing seeds, including failed clocks. Its abstract
# memory model must not be confused with the physical transport top above.
ext=json.loads((ROOT/'reports/s3-fec-extensions.json').read_text())['results']['tc8psk-compact']
build=ROOT/'build/s3-fec-extensions/tc8psk-compact'
assert sha(build/'viterbi.sv')==ext['rtl_sha256']
assert sha(build/'rs.sv')==ext['rs_rtl_sha256']
assert sha(ROOT/'rtl/s3_tc8psk_metric_folded.sv')==ext['metric_rtl_sha256']
r['standalone_FEC_abstract_memory']=ext
for filename in ('viterbi.sv','rs.sv','benchmark_top.sv'):
    shutil.copy2(build/filename,out/('standalone-'+filename))
for filename in sorted((build/'fec-mem').glob('pnr*.log')):shutil.copy2(filename,out/('standalone-'+filename.name))
paths=set(ROOT.glob('experiments/s3_tc8psk*.py'))|set(ROOT.glob('tests/test_s3_tc8psk*.py'))
paths|={ROOT/f for f in ('experiments/s3_rs_isdb.py','experiments/check_isdb_rs.py','tests/test_s3_rs_compact.py',
    'rtl/s3_tc8psk_metric_folded.sv','ci/s3_psram_benchmark.py','ci/s3_fec_extension_benchmark.py',
    'ci/s3_fec_compaction_evidence.py','ci/s3_logic_site_audit.py')}
r['source_sha256']={str(f.relative_to(ROOT)):sha(f) for f in sorted(paths)}
r['tools']={t:subprocess.run([t,'--version'],capture_output=True,text=True,check=True).stdout.strip() for t in ('yosys','nextpnr-himbaechel')}
(out/'results.json').write_text(json.dumps(r,indent=2)+'\n')
(ROOT/'reports/s3-logic-site-audit.json').write_text(json.dumps(audits,indent=2)+'\n')
print(json.dumps({n:v['minimum_required_logic_sites'] for n,v in audits.items()},indent=2))

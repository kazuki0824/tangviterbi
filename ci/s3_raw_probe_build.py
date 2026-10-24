"""Build the raw-only diagnostic with an exported ESP-IDF 5.5.1 environment."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--flash-mb',choices=(8,16),type=int,default=16)
    p.add_argument('--late-stacks',action='store_true')
    a=p.parse_args();idf=Path(os.environ['IDF_PATH']);out=ROOT/'build/s3-raw-probe'/(f'n{a.flash_mb}r8'+('-late-stacks' if a.late_stacks else ''))
    out.mkdir(parents=True,exist_ok=True)
    defaults=out/'flash.defaults';defaults.write_text(f'CONFIG_ESPTOOLPY_FLASHSIZE_{a.flash_mb}MB=y\n')
    app=ROOT/'experiments/s3_raw_probe'
    files=list(app.rglob('*.c'))+list(app.rglob('CMakeLists.txt'))+list(app.rglob('*.ld'))+[app/'sdkconfig.defaults']
    files+=list((ROOT/'experiments').glob('s3_*.c'))+list((ROOT/'experiments').glob('s3_*.h'))
    def hashes():return {str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(files)}
    before=hashes()
    cmd=[sys.executable,str(idf/'tools/idf.py'),'-B',str(out/'idf'),'-DIDF_TARGET=esp32s3','-DRAW_LATE_TASK_STACKS='+('ON' if a.late_stacks else 'OFF'),
         '-DSDKCONFIG='+str(out/'sdkconfig'),'-DSDKCONFIG_DEFAULTS='+str(app/'sdkconfig.defaults')+';'+str(defaults),'build']
    with (out/'build.log').open('w') as log:
        rc=subprocess.run(cmd,cwd=app,stdout=log,stderr=subprocess.STDOUT).returncode
    record=dict(IDF_commit=subprocess.check_output(['git','-C',str(idf),'rev-parse','HEAD'],text=True).strip(),
        source_sha256=before,source_unchanged_during_build=before==hashes(),
        flash_MB=a.flash_mb,late_task_stacks=a.late_stacks,exit_code=rc,link_succeeded=rc==0,hardware_boot_executed=False,
        scope='link-only raw storage and dormant task reservations; no firmware scheduling or board validation')
    (out/'build-result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2));print('\n'.join((out/'build.log').read_text().splitlines()[-18:]))
    return rc
if __name__=='__main__':sys.exit(main())

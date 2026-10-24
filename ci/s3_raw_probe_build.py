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
    p.add_argument('--heap-in-flash',action='store_true',help='Compare SDK-supported heap function placement without reducing buffers/stacks')
    p.add_argument('--no-phy-nvs',action='store_true',help='Full calibration at boot without NVS calibration storage')
    p.add_argument('--spi-lock-iram',action='store_true',help='Place the SDK SPI bus lock ISR helpers in IRAM')
    a=p.parse_args();idf=Path(os.environ['IDF_PATH']);out=ROOT/'build/s3-raw-probe'/(f'n{a.flash_mb}r8'+('-late-stacks' if a.late_stacks else '')+('-heap-flash' if a.heap_in_flash else '')+('-no-phy-nvs' if a.no_phy_nvs else '')+('-spi-lock-iram' if a.spi_lock_iram else ''))
    out.mkdir(parents=True,exist_ok=True)
    defaults=out/'flash.defaults';defaults.write_text(f'CONFIG_ESPTOOLPY_FLASHSIZE_{a.flash_mb}MB=y\n'+('CONFIG_HEAP_PLACE_FUNCTION_INTO_FLASH=y\n' if a.heap_in_flash else '')+('CONFIG_ESP_PHY_CALIBRATION_AND_DATA_STORAGE=n\n' if a.no_phy_nvs else '')+('CONFIG_RAW_SPI_LOCK_ISR_IN_IRAM=y\n' if a.spi_lock_iram else ''))
    app=ROOT/'experiments/s3_raw_probe'
    files=list(app.rglob('*.c'))+list(app.rglob('CMakeLists.txt'))+list(app.rglob('*.ld'))+[app/'sdkconfig.defaults',app/'main/Kconfig.projbuild']
    files+=list((ROOT/'experiments').glob('s3_*.c'))+list((ROOT/'experiments').glob('s3_*.h'))
    def hashes():return {str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(files)}
    before=hashes()
    cmd=[sys.executable,str(idf/'tools/idf.py'),'-B',str(out/'idf'),'-DIDF_TARGET=esp32s3','-DRAW_LATE_TASK_STACKS='+('ON' if a.late_stacks else 'OFF'),
         '-DSDKCONFIG='+str(out/'sdkconfig'),'-DSDKCONFIG_DEFAULTS='+str(app/'sdkconfig.defaults')+';'+str(defaults),'build']
    with (out/'build.log').open('w') as log:
        rc=subprocess.run(cmd,cwd=app,stdout=log,stderr=subprocess.STDOUT).returncode
    record=dict(IDF_commit=subprocess.check_output(['git','-C',str(idf),'rev-parse','HEAD'],text=True).strip(),
        source_sha256=before,source_unchanged_during_build=before==hashes(),
        flash_MB=a.flash_mb,late_task_stacks=a.late_stacks,heap_in_flash=a.heap_in_flash,no_phy_nvs=a.no_phy_nvs,spi_lock_iram=a.spi_lock_iram,exit_code=rc,link_succeeded=rc==0,hardware_boot_executed=False,
        scope='link-only raw storage and dormant task reservations; no firmware scheduling or board validation')
    (out/'build-result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2));print('\n'.join((out/'build.log').read_text().splitlines()[-18:]))
    return rc
if __name__=='__main__':sys.exit(main())

#!/usr/bin/env python3
"""Link the pinned upstream RF application with all new static reservations.

This deliberately retains upstream SPEC/IQS features as a conservative overlay;
it is NOT an integrated receiver and must not be flashed. The upstream app owns
core1 manually and masks interrupts. Replacing that scheduler is a separate gate.
The diagnostic uses the same IDF 5.5.1 as our actual SPI adapter. Upstream's own
25fe69f SDK pin differs: report compatibility rather than silently conflating it.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
UP=ROOT/'build/esp-sdr';OUT=ROOT/'build/s3-rf-coexist';OUT.mkdir(parents=True,exist_ok=True)
EXPECTED='e74f2a470972ec163c247f1fe88d32e08579242a'
actual=subprocess.check_output(['git','-C',str(UP),'rev-parse','HEAD'],text=True).strip()
if actual!=EXPECTED:raise SystemExit('upstream pin mismatch')
extra=UP/'main/s3_probe';extra.mkdir(exist_ok=True)
for p in ('s3_transport.c','s3_transport.h','s3_spi_transport.c','s3_spi_transport.h',
          's3_capture_bridge.c','s3_capture_bridge.h','s3_fft_tiles.c','s3_fft_tiles.h'):
    shutil.copy2(ROOT/'experiments'/p,extra/p)
s=(ROOT/'experiments/s3_memory_probe/main/memory_probe.c').read_text().replace('void app_main(void)','void s3_extras_link_probe(void)')
# Upstream already reserves exactly this physical RF interval.
s=s.replace('SOC_RESERVE_MEMORY_REGION(0x3fcb0000, 0x3fce0000, s3_rf_dump);','')
(extra/'memory_probe.c').write_text(s)
p=UP/'main/CMakeLists.txt';s=p.read_text().replace('set(dependencies esp_driver_gpio','set(dependencies esp_driver_spi esp_driver_gpio')
s+='''\n# LINK-ONLY diagnostic overlay from tangviterbi, do not flash.
target_sources(${COMPONENT_LIB} PRIVATE s3_probe/memory_probe.c s3_probe/s3_transport.c s3_probe/s3_spi_transport.c s3_probe/s3_capture_bridge.c s3_probe/s3_fft_tiles.c)
target_include_directories(${COMPONENT_LIB} PRIVATE s3_probe)
target_compile_definitions(${COMPONENT_LIB} PRIVATE PROBE_TERRESTRIAL=1 PROBE_LINKS=2 PROBE_TRANSPORT=1 PROBE_ZEROCOPY=1 PROBE_LATE_RF=1 PROBE_RING64=1 S3_RING_PAGE_COUNT=16)
target_link_options(${COMPONENT_LIB} INTERFACE "-Wl,-u,s3_extras_link_probe")
''';p.write_text(s)
# Retain RF PHY options; explicitly override module/cache/CPU configuration.
defaults=(UP/'sdkconfig.defaults.esp32s3').read_text()
defaults=defaults.replace('CONFIG_ESPTOOLPY_FLASHSIZE_2MB=y','CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y')
defaults=defaults.replace('CONFIG_FREERTOS_UNICORE=y','# CONFIG_FREERTOS_UNICORE is not set')
defaults+='\n'+(ROOT/'experiments/s3_memory_probe/sdkconfig.transport.defaults').read_text()
defaults+='\nCONFIG_SPIRAM=y\nCONFIG_SPIRAM_MODE_OCT=y\nCONFIG_SPIRAM_SPEED_80M=y\nCONFIG_ESP32S3_DATA_CACHE_32KB=y\n'
(UP/'sdkconfig.coexist.defaults').write_text(defaults)
cmd=['idf.py','-B',str(OUT/'idf'),'-DIDF_TARGET=esp32s3',
     '-DSDKCONFIG=sdkconfig.coexist','-DSDKCONFIG_DEFAULTS=sdkconfig.coexist.defaults','build']
with (OUT/'build.log').open('w') as f:rc=subprocess.run(cmd,cwd=UP,stdout=f,stderr=subprocess.STDOUT).returncode
log=(OUT/'build.log').read_text(errors='replace')
result={'scope':__doc__,'upstream_commit':actual,'upstream_requested_IDF':'25fe69f946311abdaf9ad56591f25fedbc20ac98',
        'IDF_commit':subprocess.check_output(['git','-C',os.environ['IDF_PATH'],'rev-parse','HEAD'],text=True).strip(),
        'exit_code':rc,'link_succeeded':rc==0,'symbols':{},'receiver_adopted':False,
        'functional_RF_SPI_integration':False,'safe_to_flash':False,
        'errors':[l for l in log.splitlines() if any(x in l for x in ('error:','overlap','overflowed','ASSERT'))][-40:]}
p=OUT/'idf/esp_sdr.map'
if p.exists():
    m=p.read_text(errors='replace')
    for sym in ('_bss_start','_bss_end','_iram_start','_iram_end','_data_end'):
        a=re.findall(r'^\s*(0x[0-9a-fA-F]+)\s+'+sym+r'\b',m,re.M)
        if a:result['symbols'][sym]=a[-1]
    if '_bss_end' in result['symbols']:result['static_gap_to_RF_bytes']=0x3fcb0000-int(result['symbols']['_bss_end'],16)
(OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2));print('\n'.join(log.splitlines()[-45:]))
if rc:raise SystemExit(rc)

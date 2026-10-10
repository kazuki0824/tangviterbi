#!/usr/bin/env python3
"""Link the pinned upstream RF application with all new static reservations.

This deliberately retains upstream SPEC/IQS features as a conservative overlay;
it is NOT an integrated receiver and must not be flashed. The upstream app owns
core1 manually and masks interrupts. Replacing that scheduler is a separate gate.
The diagnostic uses the same IDF 5.5.1 as our actual SPI adapter. Upstream's own
25fe69f SDK pin differs: report compatibility rather than silently conflating it.
"""
import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
PROFILE=os.environ.get('RF_PROFILE','full')
VARIANT=PROFILE
RS_OFFLOAD=PROFILE=='native-direct-phy-rs'
if RS_OFFLOAD:PROFILE='native-direct-phy'
if PROFILE not in ('full','native-phy','native-phy-flash','native-phy-psram','native-upper-fft','native-quarter-fft','native-quarter-pool4','native-quarter-romsafe','native-direct-phy'):raise SystemExit('unknown RF_PROFILE')
NATIVE=PROFILE!='full'
PSRAM=PROFILE in ('native-phy-psram','native-upper-fft','native-quarter-fft','native-quarter-pool4','native-quarter-romsafe','native-direct-phy')
UP=ROOT/'build/esp-sdr';OUT=ROOT/'build/s3-rf-coexist'/VARIANT;OUT.mkdir(parents=True,exist_ok=True)
if (OUT/'build.log').exists():
    prior=OUT/'prior-trials'/hashlib.sha256((OUT/'build.log').read_bytes()).hexdigest()[:12]
    prior.mkdir(parents=True,exist_ok=True)
    for f in ('build.log','result.json','sdkconfig'):
        if (OUT/f).exists():shutil.copy2(OUT/f,prior/f)
EXPECTED='e74f2a470972ec163c247f1fe88d32e08579242a'
actual=subprocess.check_output(['git','-C',str(UP),'rev-parse','HEAD'],text=True).strip()
if actual!=EXPECTED:raise SystemExit('upstream pin mismatch')
p=UP/'main/targets/esp32s3/receiver.c'
source=subprocess.check_output(['git','-C',str(UP),'show',EXPECTED+':main/targets/esp32s3/receiver.c'],text=True)
p.write_text(source) # Every profile starts from the immutable upstream pin.
if NATIVE:
    # A lower-bound link profile, NOT a replacement receiver. Retain upstream
    # tuning/calibration/PHY startup but omit SPEC/IQS/USB commands and the
    # manual core1 reset. New RF-bank code is linked, but not scheduled here.
    prefix=source.split('static size_t packed_size(unsigned n)')[0]
    init=source.split('void app_main(void) {',1)[1].split('    prepare_rx();',1)[0]
    init=init.replace('    usb_serial_jtag_driver_config_t usb={.tx_buffer_size=8192,.rx_buffer_size=8192};\n    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb));\n','')
    if PROFILE=='native-direct-phy':
        # Experimental SDK PHY entry, without the 802.11 MAC/packet driver.
        # The official PHY API configures common clocks/calibration; whether
        # the undocumented RF dump also needs MAC setup is a HARDWARE gate.
        init=init.split('    ESP_ERROR_CHECK(esp_event_loop_create_default());',1)[0]
        init+='    esp_phy_enable(PHY_MODEM_WIFI);\n'
        prefix='#include \"esp_phy_init.h\"\n'+prefix
    # Preserve attribution: the emitted file remains derived from GPL-3.0
    # ESPARGOS/esp-sdr. Source and build logs are retained, no binary shipped.
    p.write_text('/* Derived from ESPARGOS/esp-sdr '+EXPECTED+'; GPL-3.0.\n'
                 ' * Native PHY lower-bound LINK ONLY, no RF capture loop. */\n'+prefix+
                 '\nvoid app_main(void) {'+init+'    prepare_rx();\n}\n')
extra=UP/'main/s3_probe';extra.mkdir(exist_ok=True)
for p in ('s3_transport.c','s3_transport.h','s3_spi_transport.c','s3_spi_transport.h',
          's3_page_credit.c','s3_page_credit.h',
          's3_capture_bridge.c','s3_capture_bridge.h','s3_fft_tiles.c','s3_fft_tiles.h',
          's3_native_capture.c','s3_native_capture.h'):
    shutil.copy2(ROOT/'experiments'/p,extra/p)
if RS_OFFLOAD:
    for name in ('s3_rs_offload','s3_rs_rpc','s3_rs_workspace'):
        for suffix in ('.c','.h'):shutil.copy2(ROOT/'experiments'/(name+suffix),extra/(name+suffix))
s=(ROOT/'experiments/s3_memory_probe/main/memory_probe.c').read_text().replace('void app_main(void)','void s3_extras_link_probe(void)')
# Upstream already reserves exactly this physical RF interval.
s=s.replace('SOC_RESERVE_MEMORY_REGION(0x3fcb0000, 0x3fce0000, s3_rf_dump);','')
(extra/'memory_probe.c').write_text(s)
p=UP/'main/CMakeLists.txt';s=subprocess.check_output(['git','-C',str(UP),'show',EXPECTED+':main/CMakeLists.txt'],text=True).replace('set(dependencies esp_driver_gpio','set(dependencies esp_driver_spi '+('esp_psram ' if PSRAM else '')+'esp_driver_gpio')
s+='''\n# LINK-ONLY diagnostic overlay from tangviterbi, do not flash.
target_sources(${COMPONENT_LIB} PRIVATE s3_probe/memory_probe.c s3_probe/s3_transport.c s3_probe/s3_spi_transport.c s3_probe/s3_page_credit.c s3_probe/s3_capture_bridge.c s3_probe/s3_fft_tiles.c s3_probe/s3_native_capture.c)
target_include_directories(${COMPONENT_LIB} PRIVATE s3_probe)
target_compile_definitions(${COMPONENT_LIB} PRIVATE PROBE_TERRESTRIAL=1 PROBE_LINKS=2 PROBE_TRANSPORT=1 PROBE_ZEROCOPY=1 PROBE_LATE_RF=1 PROBE_RING64=1 S3_RING_PAGE_COUNT=16)
target_link_options(${COMPONENT_LIB} INTERFACE "-Wl,-u,s3_extras_link_probe")
'''
if PROFILE in ('native-upper-fft','native-quarter-fft','native-quarter-pool4','native-quarter-romsafe','native-direct-phy'):s+='\ntarget_compile_definitions(${COMPONENT_LIB} PRIVATE PROBE_UPPER_FFT=1)\n'
if PROFILE in ('native-quarter-fft','native-quarter-pool4','native-quarter-romsafe','native-direct-phy'):s+='\ntarget_compile_definitions(${COMPONENT_LIB} PRIVATE PROBE_QUARTER_FFT=1)\n'
if PROFILE in ('native-quarter-romsafe','native-direct-phy'):s+='\ntarget_compile_definitions(${COMPONENT_LIB} PRIVATE PROBE_ROM_SAFE=1)\n'
if RS_OFFLOAD:
    s+='\ntarget_compile_definitions(${COMPONENT_LIB} PRIVATE PROBE_RS_OFFLOAD=1)\n'
    s+='\ntarget_sources(${COMPONENT_LIB} PRIVATE s3_probe/s3_rs_offload.c s3_probe/s3_rs_rpc.c s3_probe/s3_rs_workspace.c)\n'
p.write_text(s)
# Retain RF PHY options; explicitly override module/cache/CPU configuration.
defaults=(UP/'sdkconfig.defaults.esp32s3').read_text()
defaults=defaults.replace('CONFIG_ESPTOOLPY_FLASHSIZE_2MB=y','CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y')
defaults=defaults.replace('CONFIG_FREERTOS_UNICORE=y','# CONFIG_FREERTOS_UNICORE is not set')
defaults+='\n'+(ROOT/'experiments/s3_memory_probe/sdkconfig.transport.defaults').read_text()
defaults+='\nCONFIG_SPIRAM=y\nCONFIG_SPIRAM_MODE_OCT=y\nCONFIG_SPIRAM_SPEED_80M=y\nCONFIG_ESP32S3_DATA_CACHE_32KB=y\n'
if PROFILE=='native-phy-flash':
    # RF MMIO acquisition is a different path from ordinary Wi-Fi packets.
    # Keep our SPI/packing/FFT hot code in IRAM; move optional Wi-Fi packet
    # speed-optimization code to flash. This does NOT prove RF runtime timing.
    for key in ('ESP_WIFI_IRAM_OPT','ESP_WIFI_RX_IRAM_OPT','ESP_WIFI_EXTRA_IRAM_OPT'):
        defaults=re.sub(r'^(?:# )?CONFIG_'+key+r'(?:=.*| is not set)$','',defaults,flags=re.M)
        defaults+='\n# CONFIG_'+key+' is not set\n'
if PROFILE in ('native-quarter-fft','native-quarter-pool4','native-quarter-romsafe','native-direct-phy'):
    # Reservation is a pool carved from internal heap, not extra capacity.
    # Compare 8/4 KiB pools; neither proves the later RF/driver allocations.
    pool=4096 if PROFILE in ('native-quarter-pool4','native-quarter-romsafe','native-direct-phy') else 8192
    defaults+='\nCONFIG_SPIRAM_MALLOC_RESERVE_INTERNAL='+str(pool)+'\n'
(UP/'sdkconfig.coexist.defaults').write_text(defaults)
cmd=['idf.py','-B',str(OUT/'idf'),'-DIDF_TARGET=esp32s3',
     '-DSDKCONFIG='+str(OUT/'sdkconfig'),'-DSDKCONFIG_DEFAULTS=sdkconfig.coexist.defaults','build']
with (OUT/'build.log').open('w') as f:rc=subprocess.run(cmd,cwd=UP,stdout=f,stderr=subprocess.STDOUT).returncode
log=(OUT/'build.log').read_text(errors='replace')
result={'scope':('Native RF initialization/tuning plus SPI/FFT/native-bank code and reservations; no integrated scheduler.' if NATIVE else __doc__),
        'profile':VARIANT,'esp_psram_component_required':PSRAM,'RS_offload_mode_union':RS_OFFLOAD,
        'quarter_FFT_coefficients':PROFILE in ('native-quarter-fft','native-quarter-pool4','native-quarter-romsafe','native-direct-phy'),
        'upper_FFT_slot':PROFILE in ('native-upper-fft','native-quarter-fft','native-quarter-pool4','native-quarter-romsafe','native-direct-phy'),
        'RF_bank_loop_linked':True,
        'RF_bank_loop_invoked_by_app':PROFILE=='full',
        'direct_PHY_without_80211_driver':PROFILE=='native-direct-phy',
        'direct_PHY_RF_dump_compatibility_verified':False,
        'native_PHY_only_lower_bound':NATIVE,
        'upstream_commit':actual,'upstream_requested_IDF':'25fe69f946311abdaf9ad56591f25fedbc20ac98',
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
    result['hot_functions']={}
    for name in (('s3_fft_stage_quarter_tile' if PROFILE in ('native-quarter-fft','native-quarter-pool4','native-quarter-romsafe','native-direct-phy') else 's3_fft_stage_tile'),'s3_fft_reverse_tile','s3_iq10_push','s3_spi_queue',
                 's3_rf_submit','s3_capture_accept','s3_capture_reclaim','s3_capture_step'):
        found=re.findall(r'^\s*(0x[0-9a-fA-F]+)\s+'+name+r'\s*$',m,re.M)
        if found:result['hot_functions'][name]=found[-1]
    result['inspected_hot_functions_in_IRAM']=(len(result['hot_functions'])==8 and
        all(0x40374000<=int(x,16)<0x403a0000 for x in result['hot_functions'].values()))
    result['credit_hot_functions']={}
    for name in ('s3_rf_submit_credited','s3_spi_prepare_credit_status',
                 's3_credit_status','s3_credit_reserve','s3_credit_poison'):
        found=re.findall(r'^\s*(0x[0-9a-fA-F]+)\s+'+name+r'\s*$',m,re.M)
        if found:result['credit_hot_functions'][name]=found[-1]
    result['credit_hot_functions_in_IRAM']=(len(result['credit_hot_functions'])==5 and
        all(0x40374000<=int(x,16)<0x403a0000 for x in result['credit_hot_functions'].values()))
    if RS_OFFLOAD:
        result['RS_hot_functions']={}
        for name in ('s3_rs_solve','s3_rs_magnitudes','s3_rs_rpc_syndromes','s3_rs_rpc_roots','s3_rs_rpc_crc','s3_rs_rpc_ack'):
            found=re.findall(r'^\s*(0x[0-9a-fA-F]+)\s+'+name+r'\s*$',m,re.M)
            if found:result['RS_hot_functions'][name]=found[-1]
        result['RS_inspected_hot_functions_in_IRAM']=len(result['RS_hot_functions'])==6 and all(
            0x40374000<=int(v,16)<0x403a0000 for v in result['RS_hot_functions'].values())
        found=re.findall(r'^\s*(0x[0-9a-fA-F]+)\s+fft_mode_slot1\s*$',m,re.M)
        result['RS_slot1_base']=found[-1] if found else None
        result['RS_slot1_base_aligned32']=bool(found) and int(found[-1],16)%32==0
config=OUT/'idf/config/sdkconfig.json'
if config.exists():
    values=json.loads(config.read_text())
    result['effective_config']={key:values.get(key) for key in
        ('ESP_WIFI_IRAM_OPT','ESP_WIFI_RX_IRAM_OPT','ESP_WIFI_EXTRA_IRAM_OPT',
         'SPI_MASTER_IN_IRAM','SPI_MASTER_ISR_IN_IRAM','ESP32S3_DATA_CACHE_32KB',
         'SPIRAM','SPIRAM_MODE_OCT','SPIRAM_SPEED_80M','FREERTOS_UNICORE')}
    result['requested_PSRAM_configuration_effective']=all(values.get(k) is True for k in
        ('SPIRAM','SPIRAM_MODE_OCT','SPIRAM_SPEED_80M'))
(OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if PSRAM and not result.get('requested_PSRAM_configuration_effective'):
    raise SystemExit('PSRAM configuration was not effective; no module-fit claim allowed')
print(json.dumps(result,indent=2));print('\n'.join(log.splitlines()[-45:]))
# A measured overlap is a result, not an infrastructure failure. Never turn
# compile errors or missing symbols into successful diagnostic jobs.
if rc and not any('S3 RF ring overlaps' in e for e in result['errors']):raise SystemExit(rc)

if rc==0 and not result.get("credit_hot_functions_in_IRAM"):
    raise SystemExit("credit call graph missing or outside IRAM; link is not qualified")

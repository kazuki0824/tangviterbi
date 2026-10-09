#!/usr/bin/env python3
"""Necessary startup-memory bound for the native-upper-fft IDF5.5.1 probe.

Not a simulated boot. Overestimates available memory (all RTC fast RAM and no
heap metadata) and underestimates required memory (stacks only, no TCBs,
TASK_EXTRA_STACK_SIZE, event/Wi-Fi tasks, drivers, or allocation fragmentation).
A failed bound is enough to reject this exact configuration even if it links.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

def audit(map_text,config,profile="native-upper-fft"):
    assert config['FREERTOS_NUMBER_OF_CORES']==2 and config['ESP_IPC_ENABLE']
    assert config['ESP32S3_DATA_CACHE_32KB'] and config['SPIRAM_MODE_OCT']
    assert config['ESP_SYSTEM_MEMPROT_FEATURE']
    assert config['ESP32S3_INSTRUCTION_CACHE_16KB']
    def symbol(name):
        a=re.findall(r'^\s*(0x[0-9a-f]+)\s+'+name+r'\b',map_text,re.M)
        if not a:raise ValueError('missing symbol '+name)
        return int(a[-1],16)
    heap_start=symbol('_heap_start');data_start=symbol('_data_start');iram_end=symbol('_iram_end')
    assert data_start==iram_end-0x6f0000
    assert 0x3fc88000<data_start<heap_start<0x3fcb0000
    # No unreserved upper DMA arena: raw RF [b0000,e0000), FFT0 [e0000,e8000),
    # and RF queue [e8000,f8000) cover all remaining DIRAM/DMA regions.
    dma_upper=0x3fcb0000-heap_start
    rtc_upper=8192 if config.get('ESP_SYSTEM_ALLOW_RTC_FAST_MEM_AS_HEAP') else 0
    stacks={'main':config['ESP_MAIN_TASK_STACK_SIZE'],
            'esp_timer':config['ESP_TIMER_TASK_STACK_SIZE'],
            'IPC_two_cores':2*config['ESP_IPC_TASK_STACK_SIZE'],
            'idle_two_cores':2*config['FREERTOS_IDLE_TASK_STACKSIZE']}
    minimum=sum(stacks.values());maximum=dma_upper+rtc_upper
    return {'scope':__doc__,'profile':profile,
        'map_sha256':hashlib.sha256(map_text.encode()).hexdigest(),
        'internal_DMA_heap_upper_bound_bytes':dma_upper,
        'RTC_fast_heap_generous_upper_bound_bytes':rtc_upper,
        'total_internal_heap_generous_upper_bound_bytes':maximum,
        'startup_stack_lower_bound_bytes':stacks,'total_stack_lower_bound_bytes':minimum,
        'shortage_lower_bound_bytes':max(0,minimum-maximum),
        'startup_necessary_capacity_pass':minimum<=maximum,
        'stack_only_headroom_upper_bound_bytes':maximum-minimum,
        'startup_sufficient_capacity_proven':False,
        'configured_internal_DMA_pool_target_bytes':config['SPIRAM_MALLOC_RESERVE_INTERNAL'],
        'internal_DMA_pool_has_distinct_byte_capacity':config['SPIRAM_MALLOC_RESERVE_INTERNAL']<=dma_upper,
        'heap_start':hex(heap_start),'fft_slot1':hex(symbol('fft_slot1')),
        'twiddle':hex(symbol('fft_twiddle_reservation')),
        'default_dynamic_FreeRTOS_allocation':'MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT; allowing explicit external static stacks does not relocate xTaskCreatePinnedToCore stacks',
        'sources':[f'https://github.com/espressif/esp-idf/blob/v5.5.1/components/{p}' for p in
            ('heap/port/esp32s3/memory_layout.c','freertos/heap_idf.c','freertos/port_common.c',
             'freertos/app_startup.c','esp_system/esp_ipc.c','esp_timer/src/esp_timer.c',
             'esp_system/include/esp_task.h','esp_psram/system_layer/esp_psram.c')],
        'hardware_boot_executed':False,'receiver_adopted':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--map',type=Path,required=True)
    p.add_argument('--sdkconfig',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--profile',default='native-upper-fft',choices=('native-upper-fft','native-quarter-fft'))
    a=p.parse_args();r=audit(a.map.read_text(),json.loads(a.sdkconfig.read_text()),a.profile)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))

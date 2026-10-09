#!/usr/bin/env python3
"""Necessary startup-memory bound for the native-upper-fft IDF5.5.1 probe.

Not a simulated boot. Overestimates available memory (mapped RTC fast RAM, with no
heap metadata) and underestimates required memory. Target TCB sizes are
optional, extracted from the ELF. Wi-Fi/driver allocations and fragmentation
are not included. This is a capacity bound, not a startup execution simulation.
A failed bound is enough to reject this exact configuration even if it links.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

def tcb_size_from_dwarf(text):
    # Read the target compiler's structure layout, never substitute host ABI.
    sizes = set(map(int, re.findall(r'DW_AT_name[^\n]*: xSTATIC_TCB\n[^\n]*DW_AT_byte_size\s*:\s*(\d+)', text)))
    if len(sizes) != 1:
        raise ValueError('missing or conflicting target StaticTask_t layouts')
    return sizes.pop()


def audit(map_text,config,profile="native-upper-fft",tcb_bytes=None):
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
    rtc_upper=0
    if config.get('ESP_SYSTEM_ALLOW_RTC_FAST_MEM_AS_HEAP'):
        rtc_start=symbol('_rtc_noinit_end' if config.get('ESP32S3_RTCDATA_IN_FAST_MEM') else '_rtc_force_fast_end')
        reserve_start=symbol('_rtc_reserved_start');reserve_end=symbol('_rtc_reserved_end')
        assert 0x600fe000<=rtc_start<=reserve_start<=reserve_end<=0x60100000
        rtc_upper=0x60100000-rtc_start-(reserve_end-reserve_start)
    extra = 0 if config.get('LIBC_NEWLIB_NANO_FORMAT', config.get('NEWLIB_NANO_FORMAT', False)) else 512
    stacks={'main':config['ESP_MAIN_TASK_STACK_SIZE']+extra,
            'esp_timer':config['ESP_TIMER_TASK_STACK_SIZE']+extra,
            'IPC_two_cores':2*(config['ESP_IPC_TASK_STACK_SIZE']+
                              (256 if config.get('COMPILER_OPTIMIZATION_NONE') else 0)),
            'idle_two_cores':2*config['FREERTOS_IDLE_TASK_STACKSIZE']}
    tasks = 6
    timer_impl='disabled'
    if config.get('FREERTOS_USE_TIMERS'):
        # IDF supplies a weak do-nothing constructor from tasks.c if no timer
        # API pulls timers.c into the link. Kconfig alone does NOT create it.
        match=re.search(r'\.text\.xTimerCreateTimerTask\s*\n?\s*0x[0-9a-f]+\s+0x[0-9a-f]+[^\n]*libfreertos\.a\((tasks|timers)\.c\.obj\)',map_text)
        if not match:raise ValueError('cannot identify linked FreeRTOS timer constructor')
        timer_impl=match.group(1)
    if timer_impl=='timers':
        stacks['FreeRTOS_timer'] = config['FREERTOS_TIMER_TASK_STACK_DEPTH']
        tasks += 1
    # Idle stack overhead and all allocator metadata are still omitted, so
    # this remains a necessary lower bound even in nondefault configurations.
    minimum=sum(stacks.values());maximum=dma_upper+rtc_upper
    tcb_min = tasks*(tcb_bytes or 0)
    free_before_pool_upper = min(dma_upper, maximum-minimum-tcb_min)
    pool = config['SPIRAM_MALLOC_RESERVE_INTERNAL']
    event_stack = config['ESP_SYSTEM_EVENT_TASK_STACK_SIZE']+extra
    if config.get('LWIP_TCPIP_CORE_LOCKING'): event_stack += 2048
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
        'target_StaticTask_t_bytes':tcb_bytes, 'startup_task_count':tasks,
        'FreeRTOS_timer_constructor_object':timer_impl,
        'FreeRTOS_timer_task_created':timer_impl=='timers',
        'startup_TCB_lower_bound_bytes':tcb_min,
        'task_extra_stack_bytes_per_main_and_esp_timer':extra,
        'internal_free_before_DMA_pool_upper_bound_bytes':free_before_pool_upper,
        'startup_pool_necessary_capacity_pass':free_before_pool_upper>=pool,
        'startup_pool_shortage_lower_bound_bytes':max(0,pool-free_before_pool_upper),
        'pool_allocation_order':'main task carves pool after all startup tasks are live, before app_main; do not add pool bytes again to later runtime demand',
        'native_event_stack_bytes':event_stack,
        'headroom_after_startup_tasks_and_native_event_upper_bound_bytes':maximum-minimum-tcb_min-event_stack-(tcb_bytes or 0),
        'not_counted':['heap headers/alignment/fragmentation','idle extra stack overhead',
                       'FreeRTOS timer queue if linked','event queue','Wi-Fi task and queues',
                       'Wi-Fi static RX buffers','PHY/calibration allocations',
                       'SPI/GDMA/SCT runtime objects','receiver worker stacks'],
        'configured_internal_DMA_pool_target_bytes':config['SPIRAM_MALLOC_RESERVE_INTERNAL'],
        'internal_DMA_pool_has_distinct_byte_capacity':config['SPIRAM_MALLOC_RESERVE_INTERNAL']<=dma_upper,
        'heap_start':hex(heap_start),'fft_slot1':hex(symbol('fft_slot1')),
        'twiddle':hex(symbol('fft_twiddle_reservation')),
        'default_dynamic_FreeRTOS_allocation':'MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT; allowing explicit external static stacks does not relocate xTaskCreatePinnedToCore stacks',
        'sources':[f'https://github.com/espressif/esp-idf/blob/v5.5.1/components/{p}' for p in
            ('heap/port/esp32s3/memory_layout.c','freertos/heap_idf.c','freertos/port_common.c',
             'freertos/app_startup.c','esp_system/esp_ipc.c','esp_timer/src/esp_timer.c',
             'esp_system/include/esp_task.h','esp_psram/system_layer/esp_psram.c',
             'freertos/config/include/freertos/FreeRTOSConfig.h','freertos/esp_additions/freertos_tasks_c_additions.h',
             'esp_event/default_event_loop.c',
             'esp_wifi/esp32s3/esp_adapter.c')],
        'hardware_boot_executed':False,'receiver_adopted':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--map',type=Path,required=True)
    p.add_argument('--sdkconfig',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--profile',default='native-upper-fft',choices=('native-upper-fft','native-quarter-fft'))
    p.add_argument('--elf',type=Path)
    p.add_argument('--readelf',default='readelf')
    a=p.parse_args();tcb=None
    if a.elf:
        dwarf=subprocess.check_output([a.readelf,'--debug-dump=info',str(a.elf)],text=True)
        tcb=tcb_size_from_dwarf(dwarf)
    r=audit(a.map.read_text(),json.loads(a.sdkconfig.read_text()),a.profile,tcb)
    if a.elf:r['ELF_sha256']=hashlib.sha256(a.elf.read_bytes()).hexdigest()
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))

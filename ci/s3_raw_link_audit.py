"""Audit actual raw-only SDK ELF reservations and necessary startup capacity.

Every check is accumulated. A successful link is NOT boot, allocator or WCET proof.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
from s3_rom_layout_audit import ELF32, audit as rom_audit, overlap
from s3_startup_memory_bound import allocator_refinement

ROOT=Path(__file__).resolve().parents[1]

def subtract(ranges, reserved):
    remaining=list(ranges)
    for a,b in reserved:
        new=[]
        for lo,hi in remaining:
            if not overlap((lo,hi),(a,b)):new.append((lo,hi));continue
            if lo<a:new.append((lo,min(a,hi)))
            if b<hi:new.append((max(b,lo),hi))
        remaining=new
    return remaining

def dwarf_sizes(path):
    from elftools.elf.elffile import ELFFile
    names=['spi_device_t','spi_host_t','spi_trans_priv_t','spicommon_bus_context_t',
           'spi_dma_ctx_t','Queue_t','multi_heap_info','control_t']
    found={name:set() for name in names}
    with path.open('rb') as f:
        debug=ELFFile(f).get_dwarf_info()
        for cu in debug.iter_CUs():
            for die in cu.iter_DIEs():
                attr=die.attributes.get('DW_AT_name')
                if not attr:continue
                name=attr.value.decode(errors='replace')
                if name not in found:continue
                node=die
                for _ in range(6):
                    size=node.attributes.get('DW_AT_byte_size')
                    if size:found[name].add(size.value);break
                    if 'DW_AT_type' not in node.attributes:break
                    node=node.get_DIE_from_attribute('DW_AT_type')
    if any(len(values)!=1 for values in found.values()):raise ValueError('missing/conflicting target layout: '+str(found))
    return {name:next(iter(values)) for name,values in found.items()}

def audit(elf_path, map_path, config_path, rom_path):
    types=dwarf_sizes(elf_path)
    app=ELF32(elf_path);config=json.loads(config_path.read_text());checks=[]
    def check(name,ok,detail=None):checks.append(dict(name=name,ok=bool(ok),detail=detail))
    rom=rom_audit(app,ELF32(rom_path));reserved=[(int(x['start'],16),int(x['end'],16)) for x in rom['static_reservations']]
    check('ROM_nonoverlap',rom['ROM_reservation_nonoverlap_pass'])
    for name,value in [('SPIRAM',True),('SPIRAM_MODE_OCT',True),('ESP32S3_DATA_CACHE_32KB',True),
                       ('SPI_MASTER_IN_IRAM',True),('SPI_MASTER_ISR_IN_IRAM',True),('FREERTOS_NUMBER_OF_CORES',2)]:
        check('config_'+name,config.get(name)==value,config.get(name))
    check('iram_before_RF_alias',app.address('_iram_end')<=0x403a0000)
    check('static_data_before_RF',app.address('_heap_start')<=0x3fcb0000)
    for lo,hi in [(0x3fcb0000,0x3fce0000),(0x3fce0000,0x3fce8000),(0x3fcf0000,0x3fcf8000)]:
        check('reserved_'+hex(lo),(lo,hi) in reserved)
    lower,size,_=app.symbols['raw_lower_buffers'];payload=[(lower,lower+size),(0x3fce0000,0x3fce8000),(0x3fcf0000,0x3fcf8000)]
    check('lower_two_chunks_size',size==65536)
    check('payload_alignment',all(a%4==0 for a,b in payload))
    check('payload_sum_128KiB',sum(b-a for a,b in payload)==131072)
    check('payload_before_RF_or_upper',lower>=0x3fc88000 and lower+size<=0x3fcb0000)
    check('payload_pairwise_disjoint',all(not overlap(payload[i],payload[j]) for i in range(3) for j in range(i)))
    values=struct.unpack('<10I',app.read(app.address('raw_probe_sizes'),40))
    sizes=dict(zip(['pack','capture','ports','descriptors','transfers','task_stacks','task_TCBs','StaticTask_t','DMA_descriptor','StackType_t'],values))
    check('two_static_task_stacks',sizes['task_stacks']==8192)
    check('two_static_TCBs',sizes['task_TCBs']==2*sizes['StaticTask_t'])
    stacks_addr,stacks_size,_=app.symbols['raw_task_stacks']
    late_stacks=stacks_size==8
    if late_stacks:
        pointers=struct.unpack('<2I',app.read(stacks_addr,8))
        check('late_stack_pointers',pointers==(0x3fcea000,0x3fceb000))
        check('late_stacks_reserved',(0x3fcea000,0x3fcec000) in reserved)
    else:
        check('BSS_stack_bytes',stacks_size==8192)
        check('BSS_stacks_before_RF',stacks_addr+stacks_size<=0x3fcb0000)

    hot=['s3_pp_step','s3_pp_accept','s3_pp_collect','s3_pp_reclaim','s3_pp_take','s3_pp_complete',
         's3_native_poll','s3_spi_prepare_bulk','s3_spi_queue','s3_spi_reap','s3_pp_spi_submit','s3_pp_spi_reap']
    if 'raw_keep_clocked_step' in app.symbols:
        target=struct.unpack('<I',app.read(app.address('raw_keep_clocked_step'),4))[0]
        entries={
            's3_pp_step_clocked':['s3_pp_step_clocked','s3_pp_step_impl'],
            's3_pp_step_timer':['s3_pp_step_timer','s3_pp_step_clocked_quantized',
                                's3_pp_step_impl','s3_timer_clock','esp_timer_get_time',
                                'systimer_hal_get_counter_value'],
        }
        selected=next((entry for entry in entries if entry in app.symbols and app.address(entry)==target),None)
        check('clocked_entry_known',selected is not None,hex(target))
        if selected:hot+=entries[selected]
    if 'raw_keep_cycle_clock' in app.symbols:
        target=struct.unpack('<I',app.read(app.address('raw_keep_cycle_clock'),4))[0]
        check('cycle_clock_entry_known','s3_cycle_clock_read' in app.symbols and target==app.address('s3_cycle_clock_read'))
        hot+=['s3_cycle_clock_read']
        if 's3_cycle_clock_advance' in app.symbols:hot+=['s3_cycle_clock_advance']
    if 'raw_keep_runtime_entry' in app.symbols:
        target=struct.unpack('<I',app.read(app.address('raw_keep_runtime_entry'),4))[0]
        check('runtime_entry_known','s3_raw_task_entry' in app.symbols and target==app.address('s3_raw_task_entry'))
        hot+=['s3_raw_task_entry']
    hot_symbols={name:hex(app.address(name)) if name in app.symbols else None for name in hot}
    for name in hot:check('IRAM_'+name,name in app.symbols and 0x40374000<=app.address(name)<0x403a0000)
    all_reserved=reserved+[(int(rom['ROM_reserved_start'],16),0x3fcf0000)]
    early=subtract([(0x3fc88000,0x3fce9710),(0x3fcf0000,0x3fcf8000)],all_reserved)
    late=subtract([(0x3fce9710,0x3fcf0000)],all_reserved)
    rtc=subtract([(0x600fe000,0x60100000)],all_reserved) if config.get('ESP_SYSTEM_ALLOW_RTC_FAST_MEM_AS_HEAP') else []
    early_bytes=sum(b-a for a,b in early);late_bytes=sum(b-a for a,b in late);rtc_bytes=sum(b-a for a,b in rtc)
    # SDK 5.5.1 app_startup/esp_timer add 512B unless nano libc formatting is used.
    extra=0 if config.get('LIBC_NEWLIB_NANO_FORMAT',config.get('NEWLIB_NANO_FORMAT',False)) else 512
    stacks={'main':config['ESP_MAIN_TASK_STACK_SIZE']+extra,'esp_timer':config['ESP_TIMER_TASK_STACK_SIZE']+extra,
            'IPC_two_cores':2*config['ESP_IPC_TASK_STACK_SIZE'],'idle_two_cores':2*config['FREERTOS_IDLE_TASK_STACKSIZE']}
    # Check the actual constructor implementation; Kconfig alone is insufficient.
    import re
    map_text=map_path.read_text()
    ctor=re.search(r'\.text\.xTimerCreateTimerTask\s*\n?\s*0x[0-9a-f]+\s+0x[0-9a-f]+[^\n]*libfreertos\.a\((tasks|timers)\.c\.obj\)',map_text)
    check('timer_constructor_known',bool(ctor))
    count=6
    if ctor and ctor.group(1)=='timers':stacks['FreeRTOS_timer']=config['FREERTOS_TIMER_TASK_STACK_DEPTH'];count+=1
    required=sum(stacks.values())+count*sizes['StaticTask_t']
    early_margin=early_bytes+rtc_bytes-required
    late_margin=early_margin+late_bytes
    layout={k:types[k] for k in ('multi_heap_info','control_t')};layout['pointer_bytes']=4
    early_lengths=[b-a for a,b in early];late_lengths=[b-a for a,b in late]
    # Splitting the late heap by reserved worker stacks creates extra TLSF
    # metadata. Count each region separately; do not merge across reservations.
    refined_early=allocator_refinement(early_lengths[0],rtc_bytes,count,layout,
        early_margin,0,early_dma_regions=early_lengths[1:])
    refined_final=allocator_refinement(early_lengths[0],rtc_bytes,count,layout,
        late_margin,config['SPIRAM_MALLOC_RESERVE_INTERNAL'],
        early_dma_regions=early_lengths[1:]+late_lengths)
    per_port=types['spi_host_t']+types['spicommon_bus_context_t']+types['spi_dma_ctx_t']+types['spi_device_t']
    queues=2*(types['Queue_t']+types['spi_trans_priv_t'])
    desc=2*((32768+4091)//4092)*sizes['DMA_descriptor']
    driver_lower=2*(per_port+queues+desc)
    # Reserve pool remains RAM capacity usable for DMA allocations, not a
    # separate payload charge. For headroom expose both pool-excluded free and
    # total-before-pool less known drivers, without subtracting drivers twice.
    driver=dict(type_sizes=types,per_port_objects=per_port,per_port_queue_bytes=queues,
        per_port_descriptor_bytes=desc,two_port_known_allocation_lower_bound=driver_lower,
        total_internal_after_known_driver_upper_bound=refined_final['free_before_DMA_pool_upper_bound_bytes']-driver_lower,
        not_counted=['GDMA channels/groups/pairs','bus/device locks','interrupt handles','allocation headers/alignment',
                     'PHY/calibration allocations','other runtime allocations'])
    # Preserve generous bounds. Not heap capability/order/fragmentation proof.
    startup=dict(early_internal_bytes=early_bytes,late_internal_bytes=late_bytes,RTC_generous_bytes=rtc_bytes,
        early_regions=[[hex(a),hex(b)] for a,b in early],late_regions=[[hex(a),hex(b)] for a,b in late],
        stack_lower_bound=stacks,startup_task_count=count,TCB_lower_bound=count*sizes['StaticTask_t'],
        early_headroom_upper_bound=early_margin,post_late_headroom_upper_bound=late_margin,
        main_stack_bytes=stacks['main'],
        main_stack_raw_size_candidates=[[hex(a),hex(b)] for a,b in early+rtc if b-a>=stacks['main']],
        allocation_order_and_contiguous_fit_verified=False,
        reserve_DMA_pool=config['SPIRAM_MALLOC_RESERVE_INTERNAL'],
        early_necessary_capacity_pass=early_margin>=0,
        pool_necessary_capacity_pass=min(early_bytes+late_bytes,late_margin)>=config['SPIRAM_MALLOC_RESERVE_INTERNAL'],
        allocator_early=refined_early,allocator_final=refined_final,physical_boot_verified=False,
        excluded=['heap metadata/fragmentation','driver/PHY allocations','idle task extra stack overhead','other startup allocations'])
    return dict(checks=checks,all_static_checks_pass=all(c['ok'] for c in checks),sizes=sizes,
        payload_regions=[[hex(a),hex(b)] for a,b in payload],hot_symbols=hot_symbols,
        symbols={n:hex(app.address(n)) for n in ['_iram_end','_data_start','_heap_start','raw_task_stacks','raw_task_tcbs']},
        late_task_stacks=late_stacks,startup=startup,driver_lower_bound=driver,ROM_audit=rom,
        memory_necessary_pass=all(c["ok"] for c in checks) and refined_early["pool_necessary_capacity_pass"] and refined_final["pool_necessary_capacity_pass"],ELF_sha256=hashlib.sha256(app.data).hexdigest(),
        map_sha256=hashlib.sha256(map_path.read_bytes()).hexdigest(),receiver_adopted=False,
        formal_routes=0,hardware_boot_executed=False,WCET_measured=False)

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    result=audit(a.build/'s3_raw_probe.elf',a.build/'s3_raw_probe.map',a.build/'config/sdkconfig.json',a.rom)
    build_record=json.loads((a.build.parent/'build-result.json').read_text())
    result['build']=build_record
    config=json.loads((a.build/'config/sdkconfig.json').read_text())
    result['checks'].append(dict(name='requested_flash_effective',ok=config.get(f"ESPTOOLPY_FLASHSIZE_{build_record['flash_MB']}MB")==True))
    result['checks'].append(dict(name='source_unchanged_during_build',ok=build_record['source_unchanged_during_build']))
    if 'heap_in_flash' in build_record:
        result['checks'].append(dict(name='requested_heap_placement_effective',ok=bool(config.get('HEAP_PLACE_FUNCTION_INTO_FLASH'))==build_record['heap_in_flash']))
    if 'no_phy_nvs' in build_record:
        result['checks'].append(dict(name='requested_phy_storage_effective',ok=bool(config.get('ESP_PHY_CALIBRATION_AND_DATA_STORAGE'))==(not build_record['no_phy_nvs'])))
    if build_record.get('spi_lock_iram'):
        result['checks'].append(dict(name='requested_SPI_lock_ISR_placement_effective',ok=bool(config.get('ESP_SPI_BUS_LOCK_ISR_FUNCS_IN_IRAM'))))
        app=ELF32(a.build/'s3_raw_probe.elf')
        for name in ('spi_bus_lock_bg_entry','spi_bus_lock_bg_exit','spi_bus_lock_get_acquiring_dev','spi_bus_lock_bg_clear_req','spi_bus_lock_bg_check_dev_acq','spi_bus_lock_bg_check_dev_req'):
            address=app.symbols.get(name,(0,))[0]
            result['checks'].append(dict(name='IRAM_'+name,ok=0x40374000<=address<0x403a0000,detail=hex(address)))
    if build_record.get('raw_only_spi'):
        app=ELF32(a.build/'s3_raw_probe.elf')
        for name in ('spi_device_queue_multi_trans','spi_device_get_multi_trans_result','spi_device_polling_start','spi_device_polling_end','spi_bus_multi_trans_mode_enable'):
            result['checks'].append(dict(name='raw_only_absent_'+name,ok=name not in app.symbols))
    result['all_static_checks_pass']=all(c['ok'] for c in result['checks'])
    result['memory_necessary_pass'] &= result['all_static_checks_pass']
    (a.output/'build.log.gz').write_bytes(gzip.compress((a.build.parent/'build.log').read_bytes(),mtime=0))
    for name in ['s3_raw_probe.elf','s3_raw_probe.map','config/sdkconfig.json']:
        (a.output/(Path(name).name+'.gz')).write_bytes(gzip.compress((a.build/name).read_bytes(),mtime=0))
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['all_static_checks_pass','sizes','symbols','startup']},indent=2))
    return 0 if result['all_static_checks_pass'] else 1
if __name__=='__main__':raise SystemExit(main())

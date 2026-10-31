"""Source-scoped SPI/PHY allocation ledger using the saved S3 ELF ABI.

These are requested-byte LOWER bounds and remaining-capacity UPPER bounds,
not a complete runtime heap replay or a real receiver/boot performance proof.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TYPE_NAMES = ('spicommon_bus_context_t', 'spi_dma_ctx_t', 'spi_device_t',
              'spi_host_t', 'spi_trans_priv_t', 'Queue_t', 'spi_bus_lock_t',
              'spi_bus_lock_dev_t', 'gdma_group_t', 'gdma_pair_t',
              'gdma_tx_channel_t', 'gdma_rx_channel_t', 'intr_handle_data_t',
              'vector_desc_t', 'shared_vector_desc_t', 'esp_timer',
              'esp_phy_calibration_data_t', 'heap_t_', 'multi_heap_info', 'control_t')


def target_sizes(elf_bytes):
    from elftools.elf.elffile import ELFFile
    elf = ELFFile(io.BytesIO(elf_bytes))
    if elf.elfclass != 32 or elf['e_machine'] != 'EM_XTENSA':
        raise ValueError('S3 Xtensa ELF32 required')
    found = {n: set() for n in TYPE_NAMES}
    for unit in elf.get_dwarf_info().iter_CUs():
        for die in unit.iter_DIEs():
            name = die.attributes.get('DW_AT_name')
            if not name:
                continue
            name = name.value.decode(errors='replace')
            if name not in found:
                continue
            node = die
            seen = set()
            while node.offset not in seen:
                seen.add(node.offset)
                size = node.attributes.get('DW_AT_byte_size')
                if size:
                    found[name].add(size.value)
                    break
                if 'DW_AT_type' not in node.attributes:
                    break
                node = node.get_DIE_from_attribute('DW_AT_type')
    if any(len(v) != 1 for v in found.values()):
        raise ValueError(f'missing/conflicting DWARF: {found}')
    return {n: next(iter(v)) for n, v in found.items()}


def audit(profile, config_override=None):
    raw_result = (profile / 'result.json').read_bytes()
    link = json.loads(raw_result)
    elf_bytes = gzip.decompress((profile / 's3_raw_probe.elf.gz').read_bytes())
    config_bytes = gzip.decompress((profile / 'sdkconfig.json.gz').read_bytes())
    config = json.loads(config_bytes) if config_override is None else config_override
    sizes = target_sizes(elf_bytes)
    checks = []

    def check(name, value):
        checks.append(dict(name=name, ok=bool(value)))

    check('saved_ELF_hash', hashlib.sha256(elf_bytes).hexdigest() == link['ELF_sha256'])
    check('successful_link_audit', link['all_static_checks_pass'])
    check('two_core_S3', config.get('IDF_TARGET') == 'esp32s3' and config.get('FREERTOS_NUMBER_OF_CORES') == 2)
    check('no_PM_extra_objects', not config.get('PM_ENABLE'))
    check('no_retention_extra_objects', not config.get('PM_POWER_DOWN_PERIPHERAL_IN_LIGHT_SLEEP'))
    check('no_systemview_ISR_wrapper', not config.get('APPTRACE_SV_ENABLE'))
    check('queues_are_target_84B', sizes['Queue_t'] == 84)
    check('calibration_is_target_1904B', sizes['esp_phy_calibration_data_t'] == 1904)
    check('no_partition_init_data', not config.get('ESP_PHY_INIT_DATA_IN_PARTITION'))
    check('no_multiple_init_data', not config.get('ESP_PHY_MULTIPLE_INIT_DATA_BIN'))
    check('no_reduce_TX_copy', not config.get('ESP_PHY_REDUCE_TX_POWER'))
    check('PLL_tracking_retained', not config.get('ESP_PHY_DISABLE_PLL_TRACK'))
    check('SPI_ISR_and_API_IRAM', config.get('SPI_MASTER_ISR_IN_IRAM') and config.get('SPI_MASTER_IN_IRAM'))
    check('GDMA_objects_internal', config.get('GDMA_OBJ_DRAM_SAFE'))
    check('no_extra_timer_profiling', not config.get('ESP_TIMER_PROFILING'))
    check('pinned_SDK', link['build']['IDF_commit'] == 'fcae32885b0296b32044cb99ecbdc50d98dddb83')
    check('target_allocator_layout', all(sizes[k] == v for k, v in {'heap_t_':36, 'multi_heap_info':20, 'control_t':36}.items()))
    check('DMA_pool_4KiB', config.get('SPIRAM_MALLOC_RESERVE_INTERNAL') == 4096)
    check('heap_tracking_disabled', not config.get('HEAP_TASK_TRACKING'))
    rows = []

    def row(name, count, size, source, lifetime='SPI_live', mandatory=True):
        rows.append(dict(name=name, count=count, unit_bytes=size, requested_bytes=count * size,
                         source=source, lifetime=lifetime, mandatory=mandatory))

    # Two initialized buses, one device and queue_size=1 on each, no SCT,
    # ordinary nonshared SPI IRQ, no GDMA event callbacks.
    row('bus_context', 2, sizes['spicommon_bus_context_t'], 'spi_common.c:spi_bus_initialize')
    row('DMA_context', 2, sizes['spi_dma_ctx_t'], 'spi_common.c:spicommon_dma_chan_alloc')
    descriptor_count = (32768 + 4092 - 1) // 4092
    row('TX_RX_descriptors', 4, descriptor_count * link['sizes']['DMA_descriptor'], 'spi_common.c:spicommon_dma_desc_alloc')
    row('master_host', 2, sizes['spi_host_t'], 'spi_master.c:spi_master_init_driver')
    row('device', 2, sizes['spi_device_t'], 'spi_master.c:spi_bus_add_device')
    row('TX_result_queues', 4, sizes['Queue_t'] + sizes['spi_trans_priv_t'], 'spi_master.c:spi_bus_add_device/xQueueCreate')
    row('bus_lock', 2, sizes['spi_bus_lock_t'], 'spi_bus_lock.c:spi_bus_init_lock')
    row('device_lock', 2, sizes['spi_bus_lock_dev_t'], 'spi_bus_lock.c:spi_bus_lock_register_dev')
    row('device_binary_semaphore', 2, sizes['Queue_t'], 'idf_additions.c:xQueueCreateWithCaps')
    row('GDMA_group', 1, sizes['gdma_group_t'], 'gdma.c:gdma_acquire_group_handle')
    row('GDMA_pair', 2, sizes['gdma_pair_t'], 'gdma.c:gdma_acquire_pair_handle')
    row('GDMA_TX_channel', 2, sizes['gdma_tx_channel_t'], 'gdma.c:do_allocate_gdma_channel')
    row('GDMA_RX_channel', 2, sizes['gdma_rx_channel_t'], 'gdma.c:do_allocate_gdma_channel')
    row('SPI_interrupt_handle', 2, sizes['intr_handle_data_t'], 'intr_alloc.c:esp_intr_alloc_intrstatus_bind')
    row('fresh_vector_descriptor', 2, sizes['vector_desc_t'], 'intr_alloc.c:get_desc_for_int', mandatory=False)
    row('PHY_access_mutex', 1, sizes['Queue_t'], 'phy_init.c:esp_phy_enable / newlib/src/locks.c:lock_init_generic', 'PHY_live')
    row('PHY_calibration', 1, sizes['esp_phy_calibration_data_t'], 'phy_init.c:esp_phy_load_cal_and_init', 'calibration_only')
    row('PHY_PLL_timer', 1, sizes['esp_timer'], 'phy_common.c:phy_track_pll_init / esp_timer.c:esp_timer_create', 'post_calibration')
    from s3_startup_memory_bound import allocator_refinement
    nested = allocator_refinement(4095, 0, 0, {'multi_heap_info':20, 'control_t':36, 'pointer_bytes':4}, 4095, 0)
    # SDK passes dma_heap + next_size - 1 as end, while add_region registers end-start.
    # Charge only unusable metadata, not the reusable 4096-byte pool itself.
    pool_cost = 4 + 1 + nested['allocator_overhead_lower_bound_bytes'] + sizes['heap_t_'] + 4
    totals = {}
    for fresh in (False, True):
        selected = [r for r in rows if r['mandatory'] or fresh]
        spi = [r for r in selected if r['lifetime'] == 'SPI_live']
        phy = [r for r in selected if r['lifetime'] == 'PHY_live']
        cal = spi + phy + [r for r in selected if r['lifetime'] == 'calibration_only']
        live = spi + phy + [r for r in selected if r['lifetime'] == 'post_calibration']
        # Cal_data is freed inside load_cal_and_init BEFORE PLL timer creation.
        # Do not add the transient cal buffer to the steady state, or charge
        # both transient cal and timer simultaneously as a mandatory peak.
        pre = link['startup']['allocator_final']['free_before_DMA_pool_upper_bound_bytes']
        phases = {}
        for name, phase in [('SPI_live', spi), ('PHY_calibration', cal), ('steady', live)]:
            requested = sum(r['requested_bytes'] for r in phase)
            blocks = sum(r['count'] for r in phase)
            headers = blocks * 4  # target TLSF live allocated header minimum
            phases[name] = dict(requested_bytes=requested, live_blocks=blocks,
                               allocation_headers_min_bytes=headers,
                               remaining_internal_upper_bound=pre - requested - headers - pool_cost)
        totals['fresh_vectors' if fresh else 'existing_vectors'] = phases
    return dict(scope=__doc__, input_profile=str(profile), types=sizes, checks=checks,
                all_scoped_checks_pass=all(c['ok'] for c in checks), rows=rows, phases=totals,
                DMA_pool_metadata_single_chunk_lower_bound=pool_cost,
                DMA_pool_metadata_details={'outer_allocation_header_min':4, 'exclusive_end_gap':1,
                                          'nested_allocator':nested['allocator_overhead_lower_bound_bytes'],
                                          'heap_record':sizes['heap_t_'], 'heap_record_header_min':4},
                no_phy_nvs=not bool(config.get('ESP_PHY_CALIBRATION_AND_DATA_STORAGE')),
                calibration_without_NVS='PHY_RF_CAL_FULL',
                descriptor_count_per_direction=descriptor_count,
                GDMA_transient_allocations={'duplicate_group_request': sizes['gdma_group_t'],
                                            'duplicate_pair_request': sizes['gdma_pair_t'],
                                            'lifetime': 'Sequential search temporaries freed before completing the second bus; not added to all later phases'},
                omitted=['other startup allocations/frees and all actual fragmentation',
                         'extra DMA subheap metadata if the reserve pool fragments into multiple chunks',
                         'allocator rounding/alignment beyond the 4-byte minimum',
                         'PHY binary/ROM internal behavior and any additional retained calibration copy',
                         'other lazily initialized locks/logging/libc allocations',
                         'NVS objects when storage enabled', 'shared IRQ alternative',
                         'RF-specific initialization not in esp_phy_enable'],
                cache_off_findings=[
                    {'path':'normal raw SPI ISR', 'scope':'SCT disabled; no callbacks; manual DMA alignment rejects bounce buffers; no heap allocation in normal completion path'},
                    {'path':'SCT completion ISR', 'scope':'spi_post_sct_trans calls free; not allowed for the heap-in-flash cache-off candidate'},
                    {'path':'PHY PLL tracking', 'scope':'default ESP_TIMER_TASK dispatch, not ISR; existing PHY lock is acquired by timer task'},
                    {'path':'flash read temp buffer', 'scope':'get_temp_buffer precedes cache-disabling start, release follows end in non-ROM esp_flash_api.c; IRAM attribute alone does not imply cache-off execution'},
                    {'path':'lazy libc locks', 'scope':'first acquire can allocate; other ISR locks and PHY binary/ROM paths remain unclosed'}],
                cache_off_ISR_closure_proven=False, complete_runtime_heap=False,
                hardware_boot_executed=False, receiver_adopted=False,
                source_manifest=json.loads((ROOT / 'ci/s3_runtime_memory_sources.json').read_text()),
                input_sha256={'ELF': hashlib.sha256(elf_bytes).hexdigest(),
                              'config': hashlib.sha256(config_bytes).hexdigest(),
                              'link_result': hashlib.sha256(raw_result).hexdigest()})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = audit(a.profile)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'checks': result['checks'], 'phases': result['phases']}, indent=2))
    raise SystemExit(0 if result['all_scoped_checks_pass'] else 1)

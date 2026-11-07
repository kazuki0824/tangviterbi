"""Refine retained SPI/GDMA allocations; not an allocator or boot simulation."""
import gzip,hashlib,io,json
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/s3-queue-owner'
NAMES=('gdma_tx_channel_t','gdma_rx_channel_t','gdma_pair_t','gdma_group_t','spi_bus_lock_t','spi_bus_lock_dev_t','StaticSemaphore_t','intr_handle_data_t','vector_desc_t')
def sizes(raw):
 found={n:set() for n in NAMES}
 for cu in ELFFile(io.BytesIO(raw)).get_dwarf_info().iter_CUs():
  for die in cu.iter_DIEs():
   name=die.attributes.get('DW_AT_name')
   if not name or name.value.decode(errors='replace') not in found:continue
   name=name.value.decode();node=die
   for _ in range(8):
    size=node.attributes.get('DW_AT_byte_size')
    if size:found[name].add(size.value);break
    if 'DW_AT_type' not in node.attributes:break
    node=node.get_DIE_from_attribute('DW_AT_type')
 assert all(len(v)==1 for v in found.values()),found
 return {n:next(iter(v)) for n,v in found.items()}
def audit():
 folder=OUT/'allocation-sdk';manifest=json.loads((folder/'sources.json').read_text());src={}
 for row in manifest['sources']:
  raw=gzip.decompress((folder/row['file']).read_bytes());assert hashlib.sha256(raw).hexdigest()==row['sha256']
  src[Path(row['path']).name]=raw.decode()
 # Fail closed when the archived branch/call evidence changes.
 checks={'gdma.c':['heap_caps_calloc(1, sizeof(gdma_tx_channel_t), GDMA_MEM_ALLOC_CAPS)','heap_caps_calloc(1, sizeof(gdma_rx_channel_t), GDMA_MEM_ALLOC_CAPS)','heap_caps_calloc(1, sizeof(gdma_group_t), GDMA_MEM_ALLOC_CAPS)','heap_caps_calloc(1, sizeof(gdma_pair_t), GDMA_MEM_ALLOC_CAPS)','free(pre_alloc_group);','free(pre_alloc_pair);'],
 'spi_common.c':['.flags.reserve_sibling = 1,','.sibling_chan = dma_ctx->tx_dma_chan,','SPI_GDMA_NEW_CHANNEL(&tx_alloc_config','SPI_GDMA_NEW_CHANNEL(&rx_alloc_config','spi_bus_init_lock(&bus_attr->lock'],
 'spi_bus_lock.c':['heap_caps_calloc(1, sizeof(spi_bus_lock_t)','heap_caps_calloc(1, sizeof(spi_bus_lock_dev_t)','xSemaphoreCreateBinaryWithCaps(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)'],
 'idf_additions.c':['heap_caps_malloc( sizeof( StaticSemaphore_t )','xSemaphoreCreateBinaryStatic( pxSemaphoreBuffer )'],
 'spi_master.c':['ESP_RETURN_ON_FALSE(!(trans_desc->flags & SPI_TRANS_DMA_BUFFER_ALIGN_MANUAL)', 'if (rcv_ptr && bus_attr->dma_enabled)', 'heap_caps_aligned_alloc(alignment, tx_byte_len'],
 'intr_alloc.c':['heap_caps_malloc(sizeof(intr_handle_data_t)','heap_caps_malloc(sizeof(vector_desc_t)'],
 'gdma_priv.h':['#if CONFIG_GDMA_OBJ_DRAM_SAFE','#define GDMA_MEM_ALLOC_CAPS    (MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)']}
 for f,needles in checks.items():
  for needle in needles:assert needle in src[f],(f,needle)
 elfpath=OUT/'memory-sdk/s3_queue_memory_probe.elf.gz';raw=gzip.decompress(elfpath.read_bytes())
 mem=json.loads((OUT/'memory.json').read_text());assert hashlib.sha256(raw).hexdigest()==mem['ELF_sha256']
 config=json.loads(gzip.decompress((OUT/'memory-sdk/sdkconfig.json.gz').read_bytes()))
 assert config['GDMA_OBJ_DRAM_SAFE'] and config['SOC_GDMA_NUM_GROUPS_MAX']==1
 assert not config.get('PM_ENABLE') and not config.get('APPTRACE_SV_ENABLE')
 adapter=(ROOT/'experiments/s3_raw_queue.c').read_text()
 assert 'SPI_TRANS_DMA_BUFFER_ALIGN_MANUAL' in adapter and 'memset(q->transactions,0,sizeof(q->transactions))' in adapter
 assert 't->tx_buffer=data;' in adapter and 't->rx_buffer=' not in adapter
 t=sizes(raw)
 # Both non-shared IRQ vectors and the one group must exist system-wide;
 # if already present they are not new allocations, but baseline omitted them.
 counts={n:(1 if n=='gdma_group_t' else 2) for n in NAMES}
 rows=[dict(type=n,bytes_each=t[n],retained_count=counts[n],retained_bytes=t[n]*counts[n]) for n in NAMES]
 extra=sum(r['retained_bytes'] for r in rows);old=mem['driver_lower_bound']
 r=dict(scope=__doc__,target_type_bytes=t,retained_objects=rows,additional_retained_lower_bound_bytes=extra,
  allocation_phase='RF-off initialization; retained through receive and freed at teardown, not per bank or transfer',
  fresh_two_port_gdma_allocation_calls=dict(tx=2,rx=2,group=2,pair=3,group_temporary_frees=1,pair_temporary_frees=1,condition='Initially empty GDMA group, sequential two-port setup, no concurrent clients'),
  transfer_bounce_allocation_calls=0,
  previous_known_driver_lower_bound_bytes=old['two_port_known_allocation_lower_bound'],known_driver_lower_bound_bytes=old['two_port_known_allocation_lower_bound']+extra,
  previous_internal_remaining_upper_bound_bytes=old['total_internal_after_known_driver_upper_bound'],internal_remaining_upper_bound_bytes=old['total_internal_after_known_driver_upper_bound']-extra,
  initialization_temporary_requests=[dict(type=n,bytes=t[n],reason='Preallocated before checking existing shared object; freed if object already exists. Group and pair preallocations are sequential, not summed as simultaneous.') for n in ('gdma_group_t','gdma_pair_t')],
  assumptions=['Two successful bus initializations and one device per bus; distinct non-shared SPI IRQs, no tracing wrapper.', 'One shared GDMA group counted once; two pairs each retain TX and RX even for TX-only payload.', 'System-wide retained objects counted even if an earlier subsystem created shared group/vector; do not charge them again to that subsystem.', 'No DMA callbacks registered by this SPI setup; SPI interrupt metadata counted, not four hypothetical GDMA interrupts.', 'Same retained-memory baseline as memory.json; no claim about initialization peak, allocation order or capability fit.'],
  not_counted=['Allocation headers/alignment/fragmentation','PHY/calibration and other runtime allocations','Extra IRQ sharing or other GDMA clients','Initialization CPU cost and elapsed time','Control/supervisor resources'],
  hardware_boot_executed=False,all_SoC_costs_finalized=False,source_sha256={})
 paths=[Path(__file__),ROOT/'experiments/s3_raw_queue.c',OUT/'memory.json',elfpath,OUT/'memory-sdk/sdkconfig.json.gz',folder/'sources.json']+[folder/x['file'] for x in manifest['sources']]
 r['source_sha256']={str(p.resolve().relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
 return r
if __name__=='__main__':
 r=audit();(OUT/'allocations.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ('source_sha256','assumptions','not_counted')},indent=2))

#!/usr/bin/env python3
"""Inspect actual SDK-linked RS mode storage and freeze source-hashed evidence."""
from pathlib import Path
import hashlib,json,shutil,struct,subprocess
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
b=ROOT/'build/s3-rf-coexist/native-direct-phy-rs';out=ROOT/'reports/s3-rs-link-evidence';out.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result=json.loads((b/'result.json').read_text());bound=json.loads((b/'startup-bound.json').read_text())
if not result['link_succeeded'] or not result['RS_slot1_base_aligned32'] or not result['RS_inspected_hot_functions_in_IRAM']:
 raise ValueError('RS SDK link/placement incomplete')
if sha(b/'idf/esp_sdr.elf')!=bound['ELF_sha256']:raise ValueError('stale startup ELF audit')
with (b/'idf/esp_sdr.elf').open('rb') as f:
 elf=ELFFile(f);table=elf.get_section_by_name('.symtab')
 def symbol(name):
  values=table.get_symbol_by_name(name)
  if not values or len(values)!=1:raise ValueError('missing or ambiguous ELF symbol: '+name)
  return values[0]
 s=symbol('s3_rs_workspace_layout');sec=elf.get_section(s['st_shndx']);offset=s['st_value']-sec['sh_addr']
 data=sec.data()[offset:offset+56];values=struct.unpack('<14I',data)
 fields=('slot0_union','slot1_union','slot0_RS_used','slot1_RS_used','slot0_context_offset','CRC_offset',
         'RX_offset','TX_offset','slot1_context_offset','GF_offset','slot1_RX_offset','slot1_TX_offset','context_size','GF_size')
 layout=dict(zip(fields,values));base=int(symbol('fft_mode_slot1')['st_value'])
 assert symbol('fft_mode_slot1')['st_size']==32768
 assert layout['slot0_union']==layout['slot1_union']==32768
 assert base%32==0 and base+32768<=0x3fcb0000
 pages={n:dict(address=hex((0x3fcf0000 if n in ('RX_offset','TX_offset') else base)+layout[n]),bytes=4096)
        for n in ('RX_offset','TX_offset','slot1_RX_offset','slot1_TX_offset')}
 assert all(int(p['address'],16)%32==0 for p in pages.values())
 symbols={s.name:dict(address=hex(s['st_value']),size=s['st_size']) for s in table.iter_symbols()
          if s.name.startswith(('s3_rs_','fft_mode_slot1','rf_queue_tail','fft_twiddle_reservation')) and s['st_shndx']!='SHN_UNDEF'}
 sections=[dict(name=s.name,address=hex(s['sh_addr']),size=s['sh_size']) for s in elf.iter_sections()
           if s['sh_flags']&2 and s['sh_size']]
r=dict(receiver_adopted=False,safe_to_flash=False,hardware_boot_executed=False,
 scope='SDK-linked RF/transport/FFT/RS code and reservations; capture and worker scheduler NOT integrated',
 ELF_sha256=sha(b/'idf/esp_sdr.elf'),map_sha256=sha(b/'idf/esp_sdr.map'),link=result,startup_bound=bound,
 actual_target_ABI=layout,actual_DMA_pages=pages,selected_symbols=symbols,allocated_sections=sections,
 full_runtime_allocation_verified=False,CPU_WCET_verified=False,
 source_sha256={})
paths=[ROOT/'experiments'/('s3_rs_'+name+suffix) for name in ('offload','rpc','workspace') for suffix in ('.c','.h')]
paths += [ROOT/p for p in ('experiments/s3_memory_probe/main/memory_probe.c','ci/s3_rf_coexist_probe.py',
 'ci/s3_startup_memory_bound.py','ci/s3_rs_link_evidence.py','tests/test_s3_startup_memory_bound.py')]
r['source_sha256']={str(p.relative_to(ROOT)):sha(p) for p in paths}
for source,target in ((b/'result.json','link-result.json'),(b/'startup-bound.json','startup-bound.json'),
 (b/'idf/config/sdkconfig.json','sdkconfig.json'),(b/'sdkconfig','sdkconfig'),(b/'build.log','build.log'),
 (ROOT/'build/esp-sdr/main/targets/esp32s3/receiver.c','generated-receiver.c'),
 (ROOT/'build/esp-sdr/main/CMakeLists.txt','generated-CMakeLists.txt'),
 (ROOT/'build/s3-startup-bound-final-tests.log','startup-tests.log')):
 shutil.copy2(source,out/target)
# Extract the actual DWARF definitions used for allocator/task accounting.
dwarf=subprocess.check_output(['readelf','--debug-dump=info',str(b/'idf/esp_sdr.elf')],text=True)
lines=dwarf.splitlines();snippets=[]
for i,line in enumerate(lines):
 if any(line.rstrip().endswith(': '+n) for n in ('xSTATIC_TCB','multi_heap_info','control_t')):
  snippets.extend(lines[max(0,i-1):i+6]);snippets.append('')
(out/'target-dwarf-layout.txt').write_text('\n'.join(snippets)+'\n')
(out/'results.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(dict(static_gap=result['static_gap_to_RF_bytes'],slot1_base=hex(base),DMA_pages=pages,
 free_before_DMA_pool_upper_bound=bound['allocator_refinement']['free_before_DMA_pool_upper_bound_bytes']),indent=2))

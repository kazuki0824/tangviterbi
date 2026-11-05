"""Call-closed instruction ledgers for declared pinned-ELF receiving paths."""
import argparse,json,math,re,subprocess,hashlib
from pathlib import Path
from ci.s3_sdk_cost_audit import Binary,ROOT
from ci.s3_sdk_cost_paths import declarations,rom_declarations

def audit(toolchain):
 sdk=Binary(toolchain);rom=Binary(toolchain,True)
 thunks={}
 for public,target in [(n,n) for n in ['memcpy','memset','_xtos_set_intlevel','wdt_hal_feed','wdt_hal_write_protect_enable','wdt_hal_write_protect_disable']]+[('esp_rom_route_intr_matrix','intr_matrix_set')]:
  address=int(sdk.symbols[public]['st_value']);dest=int(rom.symbols[target]['st_value'])
  text=subprocess.check_output([rom.tool,'-d',f'--start-address={address}',f'--stop-address={address+6}',str(rom.path)],env=rom.env,text=True)
  assert re.search(r'l32r\s+a9,.*\('+format(dest,'x')+r' <',text) and re.search(r'jx\s+a9',text),public
  thunks[public]=dict(address=address,target_address=dest,instructions=2)
 traces={k:sdk.trace(*v) for k,v in declarations().items()}
 traces.update({k:rom.trace(*v) for k,v in rom_declarations().items()})
 for key,name in [('validate','check_trans_valid'),('device','spi_hal_setup_device'),('hal_trans','spi_hal_setup_trans'),('format','spi_format_hal_trans_struct$isra$0'),('prepare_bulk','s3_spi_prepare_bulk')]:traces[key]=sdk.acyclic_envelope(name)
 default={t['function']:k for k,t in traces.items()}
 default.update({'memcpy':'rom_memcpy20','esp_rom_route_intr_matrix':'rom_matrix','s3_pp_take':'take_done','spi_device_get_trans_result':'sdk_result_True','s3_spi_reap':'raw_reap_2_True','xQueueReceive':'queue_receive','s3_pp_complete':'complete_8'})
 bindings={
 'bus_entry_start':{'INDIRECT:a8':'bus_intr_disable'},'bus_entry_complete':{'INDIRECT:a8':'bus_intr_disable'},
 'bus_request':{'INDIRECT:a8':'bus_intr_enable'},'bus_exit_start':{'INDIRECT:a8':'bus_intr_enable'},
 'hal_reset':{'INDIRECT:a8':'hal_ahb_reset'},'hal_start_desc':{'INDIRECT:a8':'hal_ahb_start'},
 'hal_trans':{'memcpy':'rom_memcpy48'},'prepare_bulk':{'memset':'rom_memset56'},
 'submit_empty':{'s3_pp_take':'take_empty'},'sdk_result_False':{'xQueueReceive':'queue_receive_empty'},
 'reap_idle_empty':{'s3_spi_reap':'raw_reap_2_False'},
 'raw_reap_1_False':{'spi_device_get_trans_result':'sdk_result_False'},'raw_reap_2_False':{'spi_device_get_trans_result':'sdk_result_False'},
 'spi_irq_start':{'spi_bus_lock_bg_entry':'bus_entry_start','spi_bus_lock_bg_check_dev_req':'bus_check_req_start','spi_bus_lock_bg_exit':'bus_exit_start','xQueueReceiveFromISR':'queue_receive_isr'},
 'spi_irq_complete':{'spi_bus_lock_bg_entry':'bus_entry_complete','spi_bus_lock_bg_check_dev_req':'bus_check_req_complete','spi_bus_lock_bg_exit':'bus_exit_complete','xQueueReceiveFromISR':'queue_receive_isr_empty'},
 }
 def close(key,desc=5,first=False,stack=()):
  assert key not in stack,(key,stack)
  t=traces[key];children=[]
  for call in t['calls']:
   target=call['target'];child=bindings.get(key,{}).get(target,default.get(target))
   if target=='spicommon_dma_desc_setup_link':child='dma_descriptors_'+str(desc)
   if target=='spi_new_trans':child='spi_new_'+str(first)
   assert child is not None,(key,call)
   node=close(child,desc,first,stack+(key,))
   children.append(dict(offset=call['offset'],target=target,path=child,instructions=node['inclusive_instructions'],rom_thunk_instructions=2 if child.startswith('rom_') else 0))
  return dict(own_instructions=t['own_instructions'],inclusive_instructions=t['own_instructions']+sum(c['instructions']+c['rom_thunk_instructions'] for c in children),calls=children)
 roots={}
 for desc in (5,9):
  roots[str(desc)]={k:close(k,desc) for k in ['submit_empty','submit_done','reap_idle_empty','reap_done','spi_irq_start','spi_irq_complete','wdt_mark_0','wdt_feed_0','raw_running_1','raw_running_2','feed_False','feed_True']}
  roots[str(desc)]['spi_irq_first']=close('spi_irq_start',desc,True)
 return dict(source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'ci/s3_sdk_cost_audit.py',ROOT/'ci/s3_sdk_cost_paths.py',ROOT/'ci/s3_sdk_cost_report.py']},call_bindings=bindings,default_bindings=default,verified_rom_thunks=thunks,sdk_elf_sha256=sdk.sha,rom_elf_sha256=rom.sha,alpha=1.1,roots=roots,
  paths={k:dict(function=t['function'],own_instructions=t['own_instructions'],calls=t['calls'],offsets=[p['offset'] for p in t['path']]) for k,t in traces.items()},
  conditions=['Pinned S ELF; T descriptor count is a parameter substitution, not a T ELF audit.','Single owner, one device per SPI bus, both SPI IRQs on core0, queues have no waiting task, no receive/copy/free payload path.','No critical-section contention; successful single CAS; WDT list contains exactly two tasks.','Normal equal high words in sequence counters; eight-lease full-prefix retirement envelope for reap.','ROM calls include verified two-instruction SDK-address thunks.'],
  unresolved=['IRQ entry/exit and register-window exception cost','SPI UPDATE hardware wait','Flash/cache/MMIO/DMA stalls','Other-core WDT lock contention and complete application interrupt inventory','Normal-path declaration reachability and long-counter variants'],hardware_wcet=False)

def main():
 p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,default=ROOT/'reports/s3-sdk-cost-ledger/results.json');a=p.parse_args()
 r=audit(a.toolchain.resolve());a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
 for desc,roots in r['roots'].items():print(desc,{k:v['inclusive_instructions'] for k,v in roots.items()})
if __name__=='__main__':main()

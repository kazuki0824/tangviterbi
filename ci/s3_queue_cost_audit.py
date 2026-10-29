"""Recheck saved SDK path costs against the depth-two candidate ELF."""
import argparse,gzip,hashlib,io,json,math,re
from pathlib import Path
from elftools.elf.elffile import ELFFile
from ci.s3_sdk_cost_audit import Binary,ROOT
from ci.s3_sdk_cost_paths import declarations
from ci.s3_receiver_cost_audit import bounded

def candidate(tc):
 b=Binary(tc)
 b.raw=gzip.decompress((ROOT/'reports/s3-queue-study/sdk-n16r8/s3_queue_probe.elf.gz').read_bytes())
 b.sha=hashlib.sha256(b.raw).hexdigest()
 b.elf=ELFFile(io.BytesIO(b.raw));b.symbols={s.name:s for s in b.elf.get_section_by_name('.symtab').iter_symbols()}
 b.path=ROOT/'build/queue-cost.elf';b.path.write_bytes(b.raw)
 b.cache=ROOT/'build/queue-cost-graphs.json'
 b.graphs=json.loads(b.cache.read_text())['graphs'] if b.cache.exists() and json.loads(b.cache.read_text())['sha']==b.sha else {}
 return b

def audit(tc):
 b=candidate(tc);old=Binary(tc)
 config=json.loads(gzip.decompress((ROOT/'reports/s3-queue-study/sdk-n16r8/sdkconfig.json.gz').read_bytes()))
 assert config['SPIRAM'] and config['SPIRAM_MODE_OCT'] and config['STDATOMIC_S32C1I_SPIRAM_WORKAROUND']
 saved=json.loads((ROOT/'reports/s3-sdk-cost-ledger/results.json').read_text())
 assert saved['sdk_elf_sha256']==old.sha
 decl=declarations();traces={};verified={}
 envelopes={'validate':'check_trans_valid','device':'spi_hal_setup_device','hal_trans':'spi_hal_setup_trans','format':'spi_format_hal_trans_struct$isra$0'}
 def signature(node):
  args=node['args']
  if node['op']=='l32r':
   # Preserve literal contents; symbolic function addresses may relocate.
   m=re.search(r'\(([^ ]+) <([^>]+)>\)',args)
   if m:
    sym=m[2]
    literal=('symbol:'+sym) if sym in b.symbols and sym in old.symbols else m[1]
   else:raise AssertionError(args)
   args=args.split(',')[0]+','+literal
  else:args=re.sub(r'\b[0-9a-f]+ <([^>]+)>',r'<\1>',args)
  return node['op'],args,node['size'],node['edges'],node['loop_end']
 def get(key):
  if key in traces:return traces[key]
  if key.startswith('rom_'):
   t=saved['paths'][key];traces[key]=t;return t
  t=b.acyclic_envelope(envelopes[key]) if key in envelopes else b.trace(*decl[key])
  name=t['function'];ng=b.graph(name);og=old.graph(name)
  # Compare every executed instruction including literals and branch destinations.
  for row in t['path']:
   off=row['offset'];assert signature(ng[off])==signature(og[off]),(key,name,hex(off),signature(ng[off]),signature(og[off]))
  prior=saved['paths'][key]
  assert t['own_instructions']==prior['own_instructions'] and t['calls']==prior['calls'],key
  verified[key]=dict(function=name,instructions=t['own_instructions'])
  traces[key]=t;return t
 bindings=saved['call_bindings'];defaults=saved['default_bindings']
 def close(key,desc=5,first=False):
  t=get(key);children=[]
  for c in t['calls']:
   target=c['target'];child=bindings.get(key,{}).get(target,defaults.get(target))
   if target=='spicommon_dma_desc_setup_link':child='dma_descriptors_'+str(desc)
   if target=='spi_new_trans':child='spi_new_'+str(first)
   assert child,(key,target)
   fee=close(child,desc,first)['inclusive_instructions']
   if child.startswith('rom_'):
    thunk=saved['verified_rom_thunks'][target]
    assert int(b.symbols[target]['st_value'])==thunk['address']
    fee+=2
   children.append(dict(target=target,path=child,instructions=fee))
  return dict(own_instructions=t['own_instructions'],inclusive_instructions=t['own_instructions']+sum(c['instructions'] for c in children),calls=children)
 roots={k:close(k) for k in ('sdk_queue','sdk_result_False','sdk_result_True','spi_irq_start','spi_irq_complete')}
 # Completion followed immediately by dequeue/start is one ISR invocation.
 name,ch,loops=decl['spi_irq_complete'];ch=dict(ch);ch[0x195]=0x1ad;ch[0x1b0]=0x276
 decl['spi_irq_chain']=(name,ch,loops)
 traces['spi_irq_chain']=b.trace(*decl['spi_irq_chain'])
 bindings['spi_irq_chain']={'spi_bus_lock_bg_entry':'bus_entry_complete','spi_bus_lock_bg_check_dev_req':'bus_check_req_start','spi_bus_lock_bg_exit':'bus_exit_start','xQueueReceiveFromISR':'queue_receive_isr'}
 roots['spi_irq_chain']=close('spi_irq_chain')
 roots['spi_irq_first']=close('spi_irq_start',first=True)
 # A request while a previous transfer is active can take another bus-lock path.
 atom=close('atomic_or')['inclusive_instructions'];enable=close('bus_intr_enable')['inclusive_instructions']
 request=bounded(b,'spi_bus_lock_bg_request',callees={0x21:atom,0x38:atom,0x42:enable})
 declared_request=close('bus_request')['inclusive_instructions']
 assert request['instructions']>=declared_request
 roots['sdk_queue']['inclusive_instructions']+=request['instructions']-declared_request
 roots['sdk_queue']['request_envelope_adjustment']=request['instructions']-declared_request
 take=bounded(b,'s3_pp_take');empty=bounded(b,'s3_pp_take',blocked=[0x4c])
 complete=bounded(b,'s3_pp_complete',backedges={(0x7a,0x51):8})
 wrappers={
  'submit_done':bounded(b,'s3_raw_queue_submit',forced={0x33:0x36,0x36:0x39},blocked=[8,0x24,0xe0,0x124],callees={0x30:take['instructions'],0x11d:roots['sdk_queue']['inclusive_instructions']}),
  'submit_empty':bounded(b,'s3_raw_queue_submit',forced={0x21:0x2a,0x33:0x24},blocked=[8],callees={0x30:empty['instructions']}),
  'reap_empty':bounded(b,'s3_raw_queue_reap',forced={0x2d:0x94},blocked=[0x78],callees={0x25:roots['sdk_result_False']['inclusive_instructions']}),
  'reap_done':bounded(b,'s3_raw_queue_reap',forced={0x2d:0x30,0x32:0x34,0x42:0x58,0x66:0x81},blocked=[0x78],callees={0x25:roots['sdk_result_True']['inclusive_instructions'],0x61:complete['instructions']})}
 # Read actual target ABI sizes, including both send and return queue storage.
 layouts={}
 for cu in b.elf.get_dwarf_info().iter_CUs():
  for die in cu.iter_DIEs():
   name=die.attributes.get('DW_AT_name');size=die.attributes.get('DW_AT_byte_size')
   if name and size and name.value in (b'QueueDefinition',b'spi_trans_priv_t'):
    layouts[name.value.decode()]=size.value
   if name and name.value==b'spi_trans_priv_t' and die.tag=='DW_TAG_typedef':
    layouts['spi_trans_priv_t']=die.get_DIE_from_attribute('DW_AT_type').attributes['DW_AT_byte_size'].value
 assert layouts['spi_trans_priv_t']==20
 queue_bytes=layouts['QueueDefinition']
 assert int(b.symbols['probe_queues']['st_size'])==256
 assert sum(int(old.symbols[n]['st_size']) for n in ('raw_ports','raw_descriptors','raw_transfers'))==224
 driver=(ROOT/'reports/s3-spi-wait-audit/sources/spi_master.c').read_text()
 allocator=(ROOT/'reports/s3-spi-wait-audit/sources/queue.c').read_text()
 assert driver.count('xQueueCreate(dev_config->queue_size, sizeof(spi_trans_priv_t))')==2
 assert 'pvPortMalloc( sizeof( Queue_t ) + xQueueSizeInBytes )' in allocator
 assert 'xQueueSizeInBytes = ( size_t ) ( uxQueueLength * uxItemSize )' in allocator
 memory=dict(target_layouts=layouts,queue_count=4,old_queue_requested_bytes=4*(queue_bytes+20),new_queue_requested_bytes=4*(queue_bytes+40),queue_requested_increment_bytes=80,adapter_static_increment_bytes=32,combined_requested_increment_bytes=112,allocator_rounding_and_metadata_included=False,whole_receiver_fit=False)
 fees={k:math.ceil(v['instructions']*1.1) for k,v in wrappers.items()}
 # Existing normal no-reschedule IRQ envelope: 249 instructions, once per ISR.
 irq_entry=249
 fees.update({k:math.ceil((v['inclusive_instructions']+irq_entry)*1.1) for k,v in roots.items() if k.startswith('spi_irq_')})
 return dict(roots=roots,wrappers=wrappers,bus_request_envelope=request,fees_cycles=fees,alpha=1.1,irq_entry_exit_instructions=irq_entry,verified_paths=verified,memory=memory,sdk_elf_sha256=b.sha,hardware_wcet=False,all_SoC_costs_finalized=False,conditions=['Single device per port, no waiting tasks, aligned internal DMA payload, no receive data or callbacks.','Saved ROM fees reused after fixed ROM thunk address verification.','Branch envelopes admit infeasible combinations; instructions times 1.1 are a cost model, not elapsed-cycle measurement.','Owner shell, register-window traps, stalls and final application controls remain separately unresolved.'],source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'ci/s3_sdk_cost_audit.py',ROOT/'ci/s3_sdk_cost_paths.py',ROOT/'ci/s3_receiver_cost_audit.py',ROOT/'reports/s3-sdk-cost-ledger/results.json',ROOT/'reports/s3-queue-study/sdk-n16r8/s3_queue_probe.elf.gz',ROOT/'reports/s3-queue-study/sdk-n16r8/sdkconfig.json.gz',ROOT/'reports/s3-queue-study/sdk-n16r8/provenance.json',ROOT/'experiments/s3_raw_queue.c',ROOT/'experiments/s3_raw_queue.h',ROOT/'reports/s3-spi-wait-audit/sources/spi_master.c',ROOT/'reports/s3-spi-wait-audit/sources/queue.c']})

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--toolchain',type=Path,required=True);a=ap.parse_args()
 r=audit(a.toolchain.resolve());p=ROOT/'reports/s3-queue-study/sdk-n16r8/costs.json';p.write_text(json.dumps(r,indent=2)+'\n');print(r['fees_cycles']);print(r['memory'])

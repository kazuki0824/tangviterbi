"""Reuse the ROM/allocator audit for the queue-connected storage probe.

Only symbol mapping, ABI size inputs, hot entrypoints and queue depth change.
Memory capacity is a necessary condition, not allocator success or RF boot.
"""
import argparse,copy,gzip,hashlib,io,json,os,re,subprocess,sys,tempfile
from pathlib import Path
from experiments.s3_joint_runtime import ROOT,replace

def adapted_source():
 s=(ROOT/'ci/s3_raw_link_audit.py').read_text()
 s=replace(s,"'spi_dma_ctx_t','Queue_t','multi_heap_info','control_t'", "'spi_dma_ctx_t','Queue_t','multi_heap_info','control_t','StaticTask_t','dma_descriptor_align4_t','StackType_t'")
 for a,b in [('raw_lower_buffers','queue_lower_payload'),('raw_task_stacks','queue_task_stacks'),('raw_task_tcbs','queue_task_tcbs')]:s=s.replace(a,b)
 s=replace(s,"values=struct.unpack('<10I',app.read(app.address('raw_probe_sizes'),40))", "values=(app.symbols['owner_pack'][1],app.symbols['owner_capture'][1],app.symbols['owner_queues'][1],0,0,8192,app.symbols['queue_task_tcbs'][1],types['StaticTask_t'],types['dma_descriptor_align4_t'],types['StackType_t'])")
 # This compiler folds the const stack-pointer array into create_tasks.
 s=replace(s,"stacks_addr,stacks_size,_=app.symbols['queue_task_stacks']","stacks_addr,stacks_size=0,8 # two pointer arguments verified in create_tasks")
 s=replace(s,"pointers=struct.unpack('<2I',app.read(stacks_addr,8))","pointers=VERIFIED_STACK_POINTERS")
 s=s.replace("'_heap_start','queue_task_stacks','queue_task_tcbs'","'_heap_start','create_tasks','queue_task_tcbs'")
 a=s.index("    hot=['s3_pp_step'");b=s.index("    if 'raw_keep_clocked_step'",a)
 s=s[:a]+"    hot=['s3_pp_step_impl','s3_pp_step_clocked_quantized','s3_pp_accept','s3_pp_collect','s3_pp_reclaim','s3_pp_take','s3_pp_complete','s3_native_poll_budget','s3_raw_queue_submit','s3_raw_queue_reap','s3_raw_task_entry','s3_cycle_clock_read']\n"+s[b:]
 s=replace(s,"queues=2*(types['Queue_t']+types['spi_trans_priv_t'])", "queues=2*(types['Queue_t']+2*types['spi_trans_priv_t'])")
 a=s.index("    config_size=app.symbols['raw_probe_sizes']");b=s.index('    desc=2*',a)
 s=s[:a]+"    effective=(5,16384,8) # Pinned CMake inputs, not decoded ELF constants.\n    prepare_budget=2048 # Exact generated header checked by the owner audit.\n"+s[b:]
 return s

def main(rom,tc):
 folder=ROOT/'reports/s3-queue-owner/memory-sdk';out=ROOT/'reports/s3-queue-owner'
 code=adapted_source();sys.path.insert(0,str(ROOT/'ci'))
 namespace={'__name__':'queue_memory_adapter','__file__':str(ROOT/'ci/s3_raw_link_audit.py')}
 exec(compile(code,str(ROOT/'ci/s3_raw_link_audit.py'),'exec'),namespace)
 with tempfile.TemporaryDirectory() as td:
  td=Path(td)
  for name in ('s3_queue_memory_probe.elf','s3_queue_memory_probe.map','sdkconfig.json'):(td/name).write_bytes(gzip.decompress((folder/(name+'.gz')).read_bytes()))
  dis=subprocess.check_output([str(tc/'bin/xtensa-esp-elf-objdump'),'-d','--disassemble=create_tasks',str(td/'s3_queue_memory_probe.elf')],env=dict(os.environ,XTENSA_GNU_CONFIG=str(tc/'lib/xtensa_esp32s3.so')),text=True)
  # a12 points to the two saved stack arguments; a14 is stack size in bytes.
  patterns=[r'l32r\s+a7,.*\(3fcea000 ',r's32i\s+a7, a1, 8',r'l32r\s+a7,.*\(3fceb000 ',r'l32r\s+a14,.*\(1000 ',r'addi.n\s+a12, a1, 8',r's32i.n\s+a7, a1, 12',r'call8\s+.*<s3_raw_tasks_launch>']
  positions=[re.search(p,dis).start() for p in patterns];assert positions==sorted(positions)
  namespace['VERIFIED_STACK_POINTERS']=(0x3fcea000,0x3fceb000)
  (out/'memory-create-tasks.dis').write_text(dis.replace(str(td/'s3_queue_memory_probe.elf'),'queue-memory.elf'))
  r=namespace['audit'](td/'s3_queue_memory_probe.elf',td/'s3_queue_memory_probe.map',td/'sdkconfig.json',rom)
  from ci.s3_queue_owner_audit import binary
  from elftools.elf.elffile import ELFFile
  old=binary(tc);new=copy.copy(old)
  new.path=td/'s3_queue_memory_probe.elf';new.raw=new.path.read_bytes();new.sha=hashlib.sha256(new.raw).hexdigest()
  new.elf=ELFFile(io.BytesIO(new.raw));new.symbols={s.name:s for s in new.elf.get_section_by_name('.symtab').iter_symbols()}
  new.graphs={};new.cache=td/'graphs.json'
  def signature(n):
   args=n['args']
   if n['op']=='l32r':
    m=re.search(r'\(([^ ]+) <([^>]+)>\)',args);assert m,args
    args=args.split(',')[0]+','+('symbol:'+m[2] if m[2] in old.symbols and m[2] in new.symbols else m[1])
   else:args=re.sub(r'\b[0-9a-f]+ <([^>]+)>',r'<\1>',args)
   return n['op'],args,n['size'],n['edges'],n['loop_end']
  compared={}
  for name in ('s3_raw_task_entry','poll_rf','feed','pack_slice','s3_cycle_clock_read','s3_raw_queue_submit','s3_raw_queue_reap','s3_pp_step_impl'):
   a=old.graph(name);b=new.graph(name);assert set(a)==set(b),name
   for pc in a:assert signature(a[pc])==signature(b[pc]),(name,hex(pc),signature(a[pc]),signature(b[pc]))
   compared[name]=len(a)
  r['control_and_packing_CFGs_match_cost_probe']=compared
 r['stack_pointer_evidence']='create_tasks literal loads, stores at sp+8/+12, argument a12=sp+8, a14=4096, call to s3_raw_tasks_launch; const array optimized out'
 r.update(scope=__doc__,effective_compile_configuration_source='Pinned memory-probe CMakeLists.txt and generated task header; these 4 constants are not extracted from an ELF size table.',adapted_audit_sha256=hashlib.sha256(code.encode()).hexdigest(),source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'ci/s3_raw_link_audit.py',ROOT/'ci/s3_queue_owner_audit.py',ROOT/'reports/s3-queue-owner/sdk/s3_queue_owner_probe.elf.gz',ROOT/'ci/s3_rom_layout_audit.py',ROOT/'ci/s3_startup_memory_bound.py',ROOT/'experiments/s3_queue_memory_probe/main/CMakeLists.txt',ROOT/'experiments/s3_queue_memory_probe/main/queue_memory_probe.c',ROOT/'experiments/s3_queue_tasks_source.py',folder/'s3_queue_memory_probe.elf.gz',folder/'s3_queue_memory_probe.map.gz',folder/'sdkconfig.json.gz',folder/'provenance.json']})
 (out/'memory.json').write_text(json.dumps(r,indent=2)+'\n')
 print('static checks',r['all_static_checks_pass'],'necessary capacity',r['memory_necessary_pass'])
 print('symbols',r['symbols']);print('known driver',r['driver_lower_bound'])
 for check in r['checks']:
  if not check['ok']:print('FAIL',check)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--rom',type=Path,required=True);ap.add_argument('--toolchain',type=Path,required=True);a=ap.parse_args();main(a.rom.resolve(),a.toolchain.resolve())

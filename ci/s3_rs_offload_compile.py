#!/usr/bin/env python3
"""Compile CPU RS stages for the actual S3 ISA; does not measure cycles."""
from pathlib import Path
import argparse,hashlib,json,shutil,struct,subprocess
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--cc',default='xtensa-esp32s3-elf-gcc');a=p.parse_args()
cc=Path(shutil.which(a.cc) or a.cc);prefix=str(cc)[:-3]
out=ROOT/'build/s3-rs-offload-target';out.mkdir(parents=True,exist_ok=True)
evidence=ROOT/'reports/s3-rs-offload-evidence';evidence.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r=dict(receiver_adopted=False,target='ESP32-S3',silicon_WCET_verified=False,linked_application=False,
 compiler=subprocess.check_output([str(cc),'--version'],text=True).splitlines()[0],
 toolchain_metadata='https://github.com/espressif/esp-idf/blob/v5.5.1/tools/tools.json',
 reference_toolchain_archive_sha256='e3e6dcf3d275c3c9ab0e4c8a9d93fd10e7efc035d435460576c9d95b4140c676',
 compiler_binary_sha256=sha(cc),
 sources={str(ROOT.joinpath(p).relative_to(ROOT)):sha(ROOT/p) for p in
  ('experiments/s3_rs_offload.c','experiments/s3_rs_offload.h','experiments/s3_rs_rpc.c','experiments/s3_rs_rpc.h',
   'experiments/s3_rs_workspace.c','experiments/s3_rs_workspace.h')},
 variants={},rpc_variants={},workspace_variants={})
for component,source in (('solver','s3_rs_offload.c'),('rpc','s3_rs_rpc.c'),('workspace','s3_rs_workspace.c')):
 for opt in ('Os','O2','O3'):
  obj=out/f'{component}-{opt}.o'
  flags=['-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-mlongcalls',
   '-fno-builtin-memcpy','-fno-builtin-memset','-fstack-usage','-ffunction-sections','-fdata-sections',
   '-I'+str(ROOT/'experiments')]
  subprocess.run([str(cc),*flags,'-c',str(ROOT/'experiments'/source),'-o',str(obj)],check=True)
  sizes=subprocess.check_output([prefix+'size','-A',str(obj)],text=True)
  stack=obj.with_suffix('.su').read_text()
  asm=subprocess.check_output([prefix+'objdump','-dr',str(obj)],text=True)
  sections={}
  for line in sizes.splitlines():
   words=line.split()
   if len(words)==3 and words[0].startswith('.') and words[1].isdigit():sections[words[0]]=int(words[1])
  r['variants' if component=='solver' else component+'_variants'][opt]=dict(flags=flags,object_sha256=sha(obj),sections=sections,
   code_literal_rodata_bytes=sum(v for k,v in sections.items() if k.startswith(('.text','.literal','.rodata'))),
   own_function_stack_report=stack,stack_report_excludes_callees_and_RTOS=True,
   table_storage_provided_by_caller_bytes=2832 if component=='solver' else 1024 if component=='rpc' else 0,
   solution_bytes=34,
   undefined_symbols=subprocess.check_output([prefix+'nm','-u',str(obj)],text=True))
  (evidence/f'{component}-{opt}.disasm').write_text(asm)
  (evidence/f'{component}-{opt}.sizes.txt').write_text(sizes)
  (evidence/f'{component}-{opt}.stack.txt').write_text(stack)
  if component=='workspace':
   binary=out/f'workspace-layout-{opt}.bin'
   subprocess.run([prefix+'objcopy','-O','binary','--only-section=.rodata.s3_rs_workspace_layout',str(obj),str(binary)],check=True)
   fields=('slot0_union','slot1_union','slot0_RS_used','slot1_RS_used','slot0_context_offset','CRC_offset',
           'RX_offset','TX_offset','slot1_context_offset','GF_offset','slot1_RX_offset','slot1_TX_offset','context_size','GF_size')
   layout=dict(zip(fields,struct.unpack('<14I',binary.read_bytes())))
   assert layout['slot0_union']==layout['slot1_union']==32768
   r['workspace_variants'][opt]['target_ABI_layout']=layout
(evidence/'target-compile.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:dict(code_bytes=v['code_literal_rodata_bytes'],stack=v['own_function_stack_report']) for k,v in r['variants'].items()},indent=2))

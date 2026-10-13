#!/usr/bin/env python3
"""Compile the native aligned packer for S3; instruction shape is not WCET.

The inspected helper is straight-line, eight native I10/Q10 words to twenty
bytes. Metadata, caller, page boundaries, pending bytes and RF/IRQ/API costs
are outside the helper counts. A memory-issue floor is not a throughput bound.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from s3_fft_target_bound import parse

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc',default='xtensa-esp32s3-elf-gcc')
    parser.add_argument('--sdk-elf',type=Path)
    parser.add_argument('--sdk-source',type=Path)
    args=parser.parse_args()
    cc=shutil.which(args.cc) or args.cc
    prefix=cc[:-3]
    source=ROOT/'experiments/s3_transport.c'
    build=ROOT/'build/s3-packer-evidence';build.mkdir(parents=True,exist_ok=True)
    out=ROOT/'reports/s3-packer-evidence';out.mkdir(parents=True,exist_ok=True)
    flags=['-std=gnu17','-mlongcalls','-mdisable-hardware-atomics','-fno-builtin-memcpy','-fno-builtin-memset',
           '-ffunction-sections','-fdata-sections','-fstack-usage','-Wall','-Wextra','-Werror']
    results={}
    for opt in ('O2','O3'):
        obj=build/(opt+'.o')
        subprocess.run([cc,*flags,'-'+opt,'-c',str(source),'-o',str(obj)],check=True)
        asm=subprocess.check_output([prefix+'objdump','-dr',str(obj)],text=True)
        operations=parse(asm)['pack_eight']
        if any(op.startswith(('b','j','call','loop')) for op,_ in operations.values()):
            raise ValueError('packer helper is not straight-line/no-call: inspect compiler output')
        data_loads=sum(op.startswith('l32i') for op,_ in operations.values())
        stores=sum(op.startswith('s32i') for op,_ in operations.values())
        if data_loads!=8 or stores!=5:raise ValueError('expected eight word reads and five packed writes')
        memory=sum(op.startswith(('l8','l16','l32','s8','s16','s32')) for op,_ in operations.values())
        stacks=obj.with_suffix('.su').read_text()
        result={'flags':flags+['-'+opt],'object_sha256':hashlib.sha256(obj.read_bytes()).hexdigest(),
                'helper_instruction_count':len(operations),'helper_data_word_reads':data_loads,
                'helper_packed_word_writes':stores,'helper_scalar_memory_instructions':memory,
                'helper_has_calls':False,'samples_per_helper':8,'packed_bytes_per_helper':20,
                'helper_memory_issue_cycles_per_sample_floor':memory/8,
                'own_function_stack_report':stacks,'stack_report_excludes_callees_and_RTOS':True,
                'whole_packer_cycles_per_sample':None,'CPU_WCET_verified':False}
        results[opt]=result
        (out/(opt+'.disasm.gz')).write_bytes(gzip.compress(asm.encode(),mtime=0))
    x={'scope':__doc__,'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],
       'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'variants':results,
       'source_memory_issue_basis':'reports/s3-fft-target-bound/core-isa.h: one load/store unit, no dual LS FLIX',
       'SDK_flags_subset_reproduced':True,'SDK_ELF_helper_inspected':False,
       'native_payload_changed':False,'additional_software_decimation':False,
       'additional_software_requantization':False,'receiver_adopted':False}
    if args.sdk_elf:
        if not args.sdk_source or args.sdk_source.read_bytes()!=source.read_bytes():
            raise ValueError('current source must match the SDK-generated source copy')
        asm=subprocess.check_output([prefix+'objdump','-d','--disassemble=pack_eight',str(args.sdk_elf)],text=True)
        operations=parse(asm)['pack_eight']
        if not 0x40374000<=min(operations)<=max(operations)<0x403a0000:
            raise ValueError('SDK helper is not in IRAM')
        if any(op.startswith('call') for op,_ in operations.values()):raise ValueError('SDK helper has a call')
        x['SDK_ELF_helper_inspected']=True
        x['SDK_source_equivalence_verified']=True
        x['SDK_ELF_helper']={'ELF_sha256':hashlib.sha256(args.sdk_elf.read_bytes()).hexdigest(),
            'address':hex(min(operations)),'instructions':len(operations),
            'data_word_reads':sum(op.startswith('l32i') for op,_ in operations.values()),
            'packed_word_writes':sum(op.startswith('s32i') for op,_ in operations.values()),
            'calls':0,'IRAM':True,'CPU_WCET_verified':False,'evidence':'reports/s3-packer-evidence/SDK-ELF.disasm.gz'}
        (out/'SDK-ELF.disasm.gz').write_bytes(gzip.compress(asm.encode(),mtime=0))
    (out/'result.json').write_text(json.dumps(x,indent=2)+'\n')
    print(json.dumps({o:{k:v for k,v in r.items() if not k.endswith('report') and k not in ('flags',)} for o,r in results.items()},indent=2))


if __name__=='__main__':main()

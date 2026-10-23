"""Accumulate host/target evidence; never infer S3 WCET from host execution."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ci'))
from s3_fft_target_bound import parse
OUT=ROOT/'reports/s3-parallel-pack'
BUILD=ROOT/'build/s3-parallel-pack'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cc',required=True)
    args=parser.parse_args();cc=str(Path(args.cc).resolve());prefix=cc[:-3]
    OUT.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
    checks=[];logs=[]
    def run(name,cmd,timeout=180):
        try:
            r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=timeout)
            ok=r.returncode==0;log=r.stdout+r.stderr
        except (OSError,subprocess.TimeoutExpired) as exc:ok=False;log=str(exc)
        checks.append(dict(name=name,ok=ok));logs.append(name+'\n'+'\n'.join(line.rstrip() for line in log.splitlines())+'\n')
        print(name,'OK' if ok else 'NG',flush=True)
        return ok,log
    for module in ('test_s3_parallel_pack','test_s3_native_capture','test_s3_capture_bridge','test_s3_transport','test_s3_rf_pump'):
        run(module,[sys.executable,'-m','unittest','discover','-s','tests','-p',module+'.py','-v'])
    common=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-pthread','-Iexperiments']
    ok,_=run('TSAN_compile',['cc',*common,'-fsanitize=thread','experiments/s3_parallel_pack.c',
        'tests/s3_parallel_pack_host.c','-o',str(BUILD/'tsan')])
    if ok:run('TSAN_2000banks',[str(BUILD/'tsan'),'2000'])
    helper=None
    flags=['-std=gnu17','-O2','-mlongcalls','-mdisable-hardware-atomics','-fno-builtin-memcpy',
           '-fno-builtin-memset','-fstack-usage','-Wall','-Wextra','-Werror','-Iexperiments','-Itests/s3_sdk_shim']
    sizes=BUILD/'sizes.c'
    sizes.write_text('#include "s3_parallel_capture.h"\n#include "s3_parallel_spi.h"\nconst unsigned sizes[]={sizeof(s3_parallel_pack),sizeof(s3_native_sink),sizeof(s3_native_capture),sizeof(s3_pp_bank),sizeof(s3_pp_transfer)};\n')
    asm_paths=[]
    for name,source in [('pack','experiments/s3_parallel_pack.c'),('adapter','experiments/s3_parallel_capture.c'),('spi_adapter','experiments/s3_parallel_spi.c'),('sizes',str(sizes))]:
        obj=BUILD/(name+'.o')
        ok,_=run('S3_compile_'+name,[cc,*flags,'-c',source,'-o',str(obj)])
        if not ok:continue
        ok,asm=run('S3_disassemble_'+name,[prefix+'objdump','-dr',str(obj)])
        if ok:
            (OUT/(name+'.disasm.gz')).write_bytes(gzip.compress(asm.encode(),mtime=0))
            if name=='pack':
                ops=parse(asm)['pack_eight']
                helper=dict(instructions=len(ops),source_reads=sum(op.startswith('l32i') for op,_ in ops.values()),
                    packed_word_writes=sum(op.startswith('s32i') for op,_ in ops.values()),samples=8,
                    whole_worker_WCET=None)
                checks.append(dict(name='shared_fast_helper_8reads_5stores',ok=helper['source_reads']==8 and helper['packed_word_writes']==5))
        ok,nm=run('S3_symbols_'+name,[prefix+'nm','-u',str(obj)])
        if ok:
            checks.append(dict(name=name+'_no_atomic_runtime_helpers',ok='__atomic' not in nm and '__sync' not in nm))
        (OUT/(name+'.stack.txt')).write_text(obj.with_suffix('.su').read_text())
    memory=None
    ok,_=run('S3_size_constants',[prefix+'objcopy','-O','binary','--only-section=.rodata',str(BUILD/'sizes.o'),str(BUILD/'sizes.bin')])
    if ok:
        memory=dict(zip(['packer_metadata','sink_callbacks','native_capture','per_bank_metadata','SPI_transfer_metadata'],struct.unpack('<5I',(BUILD/'sizes.bin').read_bytes())))
        memory['payload_bytes']=4*32768
        memory['old_reclaimed_free_upper_bound']=9524
        memory['remaining_after_new_metadata_and_sink_upper_bound']=9524-memory['packer_metadata']-memory['sink_callbacks']-2*memory['SPI_transfer_metadata']
        memory['SDK_link_DMA_contiguity_tasks_and_driver_verified']=False
    run('diff_check',['git','diff','--check'])
    files=['experiments/s3_parallel_pack.c','experiments/s3_parallel_pack.h',
           'experiments/s3_parallel_capture.c','experiments/s3_parallel_capture.h',
           'experiments/s3_native_capture.c','experiments/s3_native_capture.h',
           'experiments/s3_iq10_block.h','experiments/s3_transport.c',
           'tests/s3_parallel_pack_host.c','tests/s3_parallel_capture_host.c',
           'tests/test_s3_parallel_pack.py','experiments/check_s3_parallel_pack.py',
           'experiments/s3_parallel_spi.h','experiments/s3_parallel_spi.c','tests/s3_parallel_spi_host.c']
    result=dict(checks=checks,all_pass=all(c['ok'] for c in checks),memory=memory,fast_helper=helper,
        source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
        target_flags=flags,SDK_linked=False,WCET_measured=False,receiver_adopted=False,formal_routes=0)
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n');(OUT/'checks.log').write_text('\n'.join(logs).rstrip()+'\n')
    return 0 if result['all_pass'] else 1
if __name__=='__main__':sys.exit(main())

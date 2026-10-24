"""Freestanding target compile of existing packing: instruction count, not WCET."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experiments.s3_fir_accx_model import instructions

def main():
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    tc=args.toolchain.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['XTENSA_GNU_CONFIG']=str(tc/'lib/xtensa_esp32s3.so');prefix=str(tc/'bin/xtensa-esp-elf-')
    rows=[];checks=[]
    for opt in ('O2','Os'):
        obj=out/(opt+'.o')
        subprocess.run([prefix+'gcc','-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-c',str(ROOT/'experiments/s3_parallel_pack.c'),'-o',str(obj)],env=env,check=True)
        dis=subprocess.check_output([prefix+'objdump','-d','--disassemble=pack_eight',str(obj)],env=env,text=True).replace(str(obj),opt+'.o');(out/(opt+'.dis')).write_text(dis)
        code=instructions(dis,'pack_eight');n=len(code)
        loads=sum(op in ('l32i','l32i.n') for op,_ in code);stores=sum(op in ('s32i','s32i.n') for op,_ in code)
        checks.append(dict(name=opt+'_eight_input_five_output_words',passed=loads==8 and stores==5))
        rows.append(dict(optimization=opt,instructions_per_eight_samples=n,instructions_per_sample=n/8,
            input_word_loads=loads,output_word_stores=stores,literal_loads=sum(op=='l32r' for op,_ in code),
            ideal_one_issue_per_cycle_Mcycles_s_T=n*16/8,ideal_one_issue_per_cycle_Mcycles_s_S=n*40/8,
            evidence_supports_8_cycles_per_sample_WCET=False))
    r=dict(scope=__doc__,rows=rows,checks=checks,
        source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['experiments/s3_parallel_pack.c','experiments/s3_iq10_block.h']},
        limitations=['Not full SDK-linked build; literal addresses remain relocatable',
        'Caller, fast-path admission, boundary slow path and slice scheduling excluded',
        'Memory stalls, interrupt and shared-bus contention excluded',
        'Do not replace the old 8-cycle sensitivity assumption with this instruction count'])
    (out/'results.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2));return any(not c['passed'] for c in checks)
if __name__=='__main__':raise SystemExit(main())

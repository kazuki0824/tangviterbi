"""Compile and count cached-history register gather for all rational phase patterns."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experiments.s3_fir_accx_model import instructions
from experiments.s3_fir_register_schedule import generate,patterns,symbol

def main():
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);tc=args.toolchain.resolve()
    env=os.environ.copy();env['XTENSA_GNU_CONFIG']=str(tc/'lib/xtensa_esp32s3.so');prefix=str(tc/'bin/xtensa-esp-elf-')
    families=[('T',32,32,63,16),('S',16,1443,2000,40)]
    asm=''.join(generate(k,offset) for _,k,up,down,_ in families for offset in sorted(patterns(up,down)))
    src=out/'register.S';src.write_text(asm);obj=out/'register.o'
    subprocess.run([prefix+'gcc','-c',str(src),'-o',str(obj)],env=env,check=True)
    dis=subprocess.check_output([prefix+'objdump','-d',str(obj)],env=env,text=True).replace(str(obj),'register.o');(out/'register.dis').write_text(dis)
    rows=[];checks=[]
    for standard,k,up,down,rate in families:
        variants=[];counts=patterns(up,down);weighted=0
        for offset,frequency in sorted(counts.items()):
            name=symbol(k,offset);code=instructions(dis,name);n=len(code);blocks=(16+max(offset)+3)//4
            expected=9*k+8+blocks*(k//16)+(k//16-1)
            checks.append(dict(name=name,passed=n==expected and sum(op.startswith('ee.vmulas') for op,_ in code)==k))
            variants.append(dict(symbol=name,offsets=offset,batches_per_phase_cycle=frequency,instructions=n,history_vector_loads=blocks*(k//16)))
            weighted+=n*frequency
        output=rate*up/down
        rows.append(dict(standard=standard,variants=variants,phase_cycle_batches=sum(counts.values()),
            optimistic_kernel_Mcycles_s=weighted/sum(counts.values())*output/4,
            ideal_all_history_loads_and_setup_and_saves_free_Mcycles_s=9*k*output/4,
            no_tap_major_IQ_array=True,coefficient_batch_bytes=k*16,
            target_executed=False,performance_qualified=False))
    r=dict(scope=__doc__,source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),generator_sha256=hashlib.sha256((ROOT/'experiments/s3_fir_register_schedule.py').read_bytes()).hexdigest(),disassembly_sha256=hashlib.sha256((out/'register.dis').read_bytes()).hexdigest(),rows=rows,checks=checks,
        excluded_scope='This AR-mediated cached-history gather layout only; not all register permutations or FIR algorithms')
    (out/'register-audit.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2));return any(not c['passed'] for c in checks)
if __name__=='__main__':raise SystemExit(main())

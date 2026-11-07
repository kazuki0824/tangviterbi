"""Compile actual ESP32-S3 assembly and audit its finite straight-line schedule."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.s3_fir_accx_model import instructions
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    tc=args.toolchain.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['XTENSA_GNU_CONFIG']=str(tc/'lib/xtensa_esp32s3.so')
    prefix=tc/'bin/xtensa-esp-elf-';src=ROOT/'experiments/s3_fir_accx.S';obj=out/'accx.o'
    subprocess.run([str(prefix)+'gcc','-c',str(src),'-o',str(obj)],env=env,check=True)
    dis=subprocess.check_output([str(prefix)+'objdump','-d',str(obj)],env=env,text=True)
    dis=dis.replace(str(obj),'accx.o');(out/'accx.dis').write_text(dis)
    rows=[];checks=[]
    for k,standard,rate,expected in [(16,'S',28.86,23),(32,'T',512/63,29)]:
        code=instructions(dis,'s3_fir_accx_'+str(k));count=len(code)
        mac=sum(op.startswith('ee.vmulas.') for op,_ in code)
        checks.extend([dict(name=standard+'_instruction_count',passed=count==expected),dict(name=standard+'_MAC_count',passed=mac==2*k//8)])
        rows.append(dict(standard=standard,taps=k,instructions_per_complex_output=count,MAC_instructions=mac,
            optimistic_one_issue_per_cycle_Mcycles_s=count*rate,
            optimistic_two_core_utilization_percent=count*rate/480*100,
            without_entry_zero_shift_setup_return_Mcycles_s=(count-3)*rate,
            history_bytes_loaded_per_output=2*(k//8+1)*16,coefficient_bytes_loaded_per_output=2*k,
            output_bytes_stored_per_output=8,target_runtime_measured=False))
    r=dict(scope=__doc__,compiler=subprocess.check_output([str(prefix)+'gcc','--version'],env=env,text=True).splitlines()[0],
        source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),object_sha256=hashlib.sha256(obj.read_bytes()).hexdigest(),
        disassembly_sha256=hashlib.sha256((out/'accx.dis').read_bytes()).hexdigest(),rows=rows,checks=checks,
        exclusions=['unpack and history writes','caller call instruction','phase selection','final Q15 conversion','DMA/RTOS/control','pipeline stalls, cache and contention'],
        runtime_execution_verified=False,all_SIMD_algorithms_excluded=False)
    (out/'accx-audit.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2));return any(not c['passed'] for c in checks)
if __name__=='__main__':raise SystemExit(main())

"""Compile the actual native source with minimal SDK declaration stubs; not an SDK link."""
import argparse, hashlib, json, os, re, subprocess
from pathlib import Path
from ci.s3_pack_cfg_audit import ROW
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 out=a.output;out.mkdir(parents=True,exist_ok=True);build=ROOT/'build/native-fill-target';stubs=build/'stubs';(stubs/'soc').mkdir(parents=True,exist_ok=True)
 declarations={'esp_attr.h':'#define IRAM_ATTR __attribute__((section(".iram1")))\n','esp_cpu.h':'#include <stdint.h>\nstatic inline uint32_t esp_cpu_get_cycle_count(void){uint32_t t;__asm__ volatile("rsr.ccount %0":"=a"(t));return t;}\n','soc/soc.h':'#define REG_READ(a) (*(volatile uint32_t *)(a))\n#define REG_WRITE(a,v) (*(volatile uint32_t *)(a)=(v))\n'}
 for name,text in declarations.items():(stubs/name).write_text(text)
 tc=a.toolchain.resolve();env=os.environ.copy();env['XTENSA_GNU_CONFIG']=str(tc/'lib/xtensa_esp32s3.so');prefix=tc/'bin/xtensa-esp-elf-';src=ROOT/'experiments/s3_native_capture.c';obj=build/'native.o'
 flags=['-O2','-std=c11','-DESP_PLATFORM','-I'+str(stubs),'-I'+str(ROOT/'experiments')]
 subprocess.run([str(prefix)+'gcc',*flags,'-c',str(src),'-o',str(obj)],env=env,check=True)
 dis=subprocess.check_output([str(prefix)+'objdump','-d',str(obj)],env=env,text=True)
 match=re.search(r'^([0-9a-f]+) <(fill[^>]+)>:\n(.*?)(?=\n[0-9a-f]+ <)',dis,re.M|re.S)
 if not match:raise ValueError('fill symbol not found')
 rows=[(int(m[1],16),m[3],m[4]) for line in match[3].splitlines() if (m:=ROW.match(line)) and m[3]!='ill']
 loop=next(i for i,r in enumerate(rows) if r[1]=='loop');end=int(re.search(r', ([0-9a-f]+) <',rows[loop][2])[1],16)
 body=[r for r in rows[loop+1:] if r[0]<end]
 checks=[dict(name='three_instruction_body',passed=[r[1] for r in body]==['memw','s32i.n','addi.n']),dict(name='fill_shape_25_instructions',passed=len(rows)==25)]
 # This emitted clone serves the nonzero constant-length production callers.
 # 7 entry + 2 exit; 10 span setup + 3 span end; 3 instructions per word.
 rows_out=[]
 for standard,rate in [('T',16),('S',40)]:
  rows_out.append(dict(standard=standard,body_instructions_per_bank=3*7168,fill_instructions_per_bank_range=[3*7168+18+13*2,3*7168+18+13*4],body_ideal_us=3*7168/240,nominal_body_Minstructions_s=rate*3*7168/12288))
 report=dict(scope=__doc__,source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),compiler=subprocess.check_output([str(prefix)+'gcc','--version'],env=env,text=True).splitlines()[0],flags=flags[:3],declaration_stubs=declarations,checks=checks,rows=rows_out,bank_callback_body_included=False,caller_and_stalls_included=False,SDK_link_verified=False,WCET_proven=False)
 (out/'target.json').write_text(json.dumps(report,indent=2)+'\n');(out/'fill.dis').write_text(match[0]);print(json.dumps(report,indent=2));return any(not c['passed'] for c in checks)
if __name__=='__main__':raise SystemExit(main())

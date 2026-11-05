"""Compile the actual native source with minimal SDK declaration stubs; not an SDK link."""
import argparse, hashlib, json, os, re, subprocess
from pathlib import Path
from ci.s3_pack_cfg_audit import ROW
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--unroll',type=int,choices=[1,4,8],default=8);p.add_argument('--prepare-quantum',type=int,default=0);a=p.parse_args()
 if a.prepare_quantum<0:raise ValueError('negative quantum')
 out=a.output;out.mkdir(parents=True,exist_ok=True);build=ROOT/'build/native-fill-target';stubs=build/'stubs';(stubs/'soc').mkdir(parents=True,exist_ok=True)
 declarations={'esp_attr.h':'#define IRAM_ATTR __attribute__((section(".iram1")))\n','esp_cpu.h':'#include <stdint.h>\nstatic inline uint32_t esp_cpu_get_cycle_count(void){uint32_t t;__asm__ volatile("rsr.ccount %0":"=a"(t));return t;}\n','soc/soc.h':'#define REG_READ(a) (*(volatile uint32_t *)(a))\n#define REG_WRITE(a,v) (*(volatile uint32_t *)(a)=(v))\n'}
 for name,text in declarations.items():(stubs/name).write_text(text)
 tc=a.toolchain.resolve();env=os.environ.copy();env['XTENSA_GNU_CONFIG']=str(tc/'lib/xtensa_esp32s3.so');prefix=tc/'bin/xtensa-esp-elf-';src=ROOT/'experiments/s3_native_capture.c';obj=build/'native.o'
 flags=['-O2','-std=c11','-DESP_PLATFORM','-DS3_NATIVE_FILL_UNROLL='+str(a.unroll),'-I'+str(stubs),'-I'+str(ROOT/'experiments')]
 subprocess.run([str(prefix)+'gcc',*flags,'-c',str(src),'-o',str(obj)],env=env,check=True)
 dis=subprocess.check_output([str(prefix)+'objdump','-d',str(obj)],env=env,text=True)
 match=re.search(r'^([0-9a-f]+) <(fill[^>]+)>:\n(.*?)(?=\n[0-9a-f]+ <)',dis,re.M|re.S)
 if not match:raise ValueError('fill symbol not found')
 rows=[(int(m[1],16),m[3],m[4]) for line in match[3].splitlines() if (m:=ROW.match(line)) and m[3]!='ill']
 loops=[];body_addresses=set()
 for i,r in enumerate(rows):
  if r[1]!='loop':continue
  end=int(re.search(r', ([0-9a-f]+) <',r[2])[1],16)
  body=[x for x in rows[i+1:] if x[0]<end];loops.append(body)
  body_addresses.update(x[0] for x in body)
 # GCC emits a branch-controlled remainder loop for the four-word variant.
 for r in rows:
  if r[1]=='bne':
   target=int(re.search(r', ([0-9a-f]+) <',r[2])[1],16)
   if target<r[0]:
    body=[x for x in rows if target<=x[0]<=r[0]]
    loops.append(body);body_addresses.update(x[0] for x in body)
 expected=[['memw','s32i.n']*a.unroll+['addi' if a.unroll>1 else 'addi.n']]
 if a.unroll>1:expected.append(['memw','s32i.n','addi.n']+(['bne'] if a.unroll==4 else []))
 checks=[dict(name='ordered_barrier_store_loop_bodies',passed=[[r[1] for r in body] for body in loops]==expected)]
 if a.unroll>1:
  offsets=[int(re.search(r', (\d+)$',r[2])[1]) for r in loops[0] if r[1]=='s32i.n']
  checks.append(dict(name='unroll_offsets',passed=offsets==list(range(0,4*a.unroll,4))))
 # Charge EVERY static non-body instruction once per span, even mutually
 # exclusive paths and repeated prologue/epilogue. This bounds instruction
 # counts, not bus stalls/cycles. Outer loop only re-enters at a new span.
 overhead=len([r for r in rows if r[0] not in body_addresses])
 def cost(at,n):
  total=0
  while n:
   span=min(16384-at,n)
   total+=(2*a.unroll+1)*(span//a.unroll)+(len(loops[-1]) if a.unroll>1 else 3)*(span%a.unroll)+overhead
   n-=span;at=0
  return total
 single=[]
 def scheduled(at,n):
  total=0
  while n:
   take=min(n,a.prepare_quantum) if a.prepare_quantum else n
   value=cost(at,take);single.append(value);total+=value
   at=(at+take)%16384;n-=take
  return total
 costs=[scheduled(at,3072)+scheduled((at+12288)%16384,4096) for at in range(16384)]
 rows_out=[]
 for standard,rate in [('T',16),('S',40)]:
  rows_out.append(dict(standard=standard,fill_instruction_envelope_per_bank=max(costs),
   span_envelope_range=[min(costs),max(costs)],fill_envelope_Minstructions_s=rate*max(costs)/12288))
 report=dict(scope=__doc__,source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),compiler=subprocess.check_output([str(prefix)+'gcc','--version'],env=env,text=True).splitlines()[0],flags=flags[:4],unroll=a.unroll,prepare_quantum_words=a.prepare_quantum,maximum_fill_call_instruction_envelope=max(single),nonbody_instructions_per_span_envelope=overhead,static_instructions=len(rows),loop_body_ops=[[r[1] for r in body] for body in loops],origin_cases=len(costs),instruction_envelope_not_WCET=True,declaration_stubs=declarations,checks=checks,rows=rows_out,bank_callback_body_included=False,caller_and_stalls_included=False,SDK_link_verified=False,WCET_proven=False)
 (out/'target.json').write_text(json.dumps(report,indent=2)+'\n');(out/'fill.dis').write_text(match[0]);print(json.dumps(report,indent=2));return any(not c['passed'] for c in checks)
if __name__=='__main__':raise SystemExit(main())

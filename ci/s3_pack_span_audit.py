"""Compile current caller and audit the contiguous-loop instructions, not WCET."""
import argparse,hashlib,json,os,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experiments.s3_fir_accx_model import instructions

def main():
 p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 tc=a.toolchain.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 env=os.environ.copy();env['XTENSA_GNU_CONFIG']=str(tc/'lib/xtensa_esp32s3.so');prefix=str(tc/'bin/xtensa-esp-elf-');rows=[];checks=[]
 for opt in ['O2','Os']:
  obj=out/(opt+'.o');subprocess.run([prefix+'gcc','-std=c11','-'+opt,'-Wall','-Wextra','-Werror','-c',str(ROOT/'experiments/s3_parallel_pack.c'),'-o',str(obj)],env=env,check=True)
  dis=subprocess.check_output([prefix+'objdump','-d',str(obj)],env=env,text=True).replace(str(obj),opt+'.o');(out/(opt+'.dis')).write_text(dis)
  code=[]
  for line in dis.splitlines():
   m=re.match(r'\s*([0-9a-f]+):\s+[0-9a-f]+\s+(\S+)\s*(.*)',line)
   if m:code.append((int(m[1],16),m[2],m[3]))
  candidates=[]
  for end,op,args in code:
   if op!='bne':continue
   target=re.search(r',\s*([0-9a-f]+)\s+<',args)
   if not target:continue
   start=int(target[1],16)
   if start>=end:continue
   loop=[x for x in code if start<=x[0]<=end]
   calls=[x for x in loop if x[1]=='call8' and '<pack_eight>' in x[2]]
   if len(calls)==1:candidates.append(loop)
  if not candidates:raise RuntimeError('no recognized contiguous loop')
  loop=min(candidates,key=len);pack=instructions(dis,'pack_eight');n=len(loop)+len(pack)
  # No boundary calculations/memory loads in the steady caller loop.
  passed=all(x[1] in ('mov.n','addi','call8','bne') or (x[1] in ('l32i.n','s32i.n') and ', a1,' in x[2]) for x in loop)
  checks.append(dict(name=opt+'_no_repeated_boundary_arithmetic',passed=passed))
  rows.append(dict(optimization=opt,loop=[dict(address=hex(x),op=y,operands=z) for x,y,z in loop],caller_instructions=len(loop),pack_instructions=len(pack),total_per_eight_samples=n,
    ideal_cycles_per_sample=n/8,ideal_Mcycles_s_T=n*16/8,ideal_Mcycles_s_S=n*40/8,
    boundary_setup_clock_stalls_included=False))
 r=dict(scope=__doc__,rows=rows,checks=checks,source_sha256=hashlib.sha256((ROOT/'experiments/s3_parallel_pack.c').read_bytes()).hexdigest(),eight_cycles_per_sample_WCET_proven=False)
 (out/'results.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2));return any(not c['passed'] for c in checks)
if __name__=='__main__':raise SystemExit(main())

"""Compare compiled steady block loops; do not extrapolate to full slice WCET."""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
from experiments.s3_joint_runtime import ROOT
from ci.s3_pack_cfg_audit import ROW

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--toolchain',type=Path,required=True);a=ap.parse_args();tc=a.toolchain.resolve();env=dict(os.environ,XTENSA_GNU_CONFIG=str(tc/'lib/xtensa_esp32s3.so'))
 out=ROOT/'reports/s3-inline-packing';out.mkdir(exist_ok=True);build=ROOT/'build/inline-packing';build.mkdir(exist_ok=True,parents=True);rows=[]
 for opt in ('O2','Os'):
  for name,source in [('baseline','s3_parallel_pack.c'),('inline','s3_inline_pack.c')]:
   obj=build/f'{name}-{opt}.o';subprocess.run([str(tc/'bin/xtensa-esp-elf-gcc'),'-std=c11','-'+opt,'-I'+str(ROOT/'experiments'),'-Wall','-Wextra','-Werror','-c',str(ROOT/'experiments'/source),'-o',str(obj)],env=env,check=True)
   dis=subprocess.check_output([str(tc/'bin/xtensa-esp-elf-objdump'),'-d',str(obj)],env=env,text=True)
   (out/f'{name}-{opt}.dis').write_text(dis.replace(str(obj),obj.name))
   with obj.open('rb') as f:
    e=ELFFile(f);syms={s.name:(int(s['st_value']),int(s['st_size'])) for s in e.get_section_by_name('.symtab').iter_symbols()}
   start,size=syms['s3_pp_step_impl'];nodes={}
   for line in dis.splitlines():
    m=ROW.match(line)
    if m:
     pc=int(m[1],16)
     if start<=pc<start+size:nodes[pc]=(m[3],m[4],len(m[2])//2)
   candidates=[]
   for pc,(op,args,length) in nodes.items():
    match=re.search(r'\b([0-9a-f]+)\s+<',args)
    if not match:continue
    target=int(match[1],16)
    if op=='loop':lo,hi=pc+length,target
    elif op.startswith('b') and target<pc:lo,hi=target,pc+length
    else:continue
    block=[(k,*v[:2]) for k,v in sorted(nodes.items()) if lo<=k<hi]
    stores=sum(v[1] in ('s32i','s32i.n') and ', a1,' not in v[2] for v in block)
    calls=[v for v in block if v[1].startswith('call') and '<pack_eight>' in v[2]]
    if stores==5 or len(calls)==1:
     callee=0
     if calls:
      st,sz=syms['pack_eight'];callee=sum(bool((m:=ROW.match(line))) and st<=int(m[1],16)<st+sz for line in dis.splitlines())
     candidates.append({'start':lo,'end':hi,'loop_instructions':len(block),'callee_instructions':callee,'total_per_eight_samples':len(block)+callee,'body':block})
   assert len(candidates)==1,(name,opt,len(candidates))
   rows.append({'variant':name,'optimization':opt,'step_text_bytes':size,'step_stack_entry':nodes[start][1],**candidates[0]})
 r={'rows':rows,'full_slice_cost_audited':False,'hardware_wcet':False,'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'experiments/s3_parallel_pack.c',ROOT/'experiments/s3_iq10_block.h',ROOT/'experiments/s3_iq10_inline.h',ROOT/'experiments/s3_inline_pack.c']}}
 (out/'instructions.json').write_text(json.dumps(r,indent=2)+'\n');print([(r['variant'],r['optimization'],r['total_per_eight_samples'],r['step_text_bytes'],r['step_stack_entry']) for r in rows])
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Optimistic scalar memory-issue bound for the actual GCC O3 FFT object.

Enumerate all CFG branch choices; mutually inconsistent branches are allowed,
so the shortest path is a lower bound. Ignore entry/return, reverse, call and
branch latencies, RF, memory stalls and synchronization. Not a WCET estimate.
"""
import argparse
import hashlib
import heapq
import json
from pathlib import Path
import re
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]

def parse(text):
 functions={};name=None
 for line in text.splitlines():
  heading=re.match(r'^([0-9a-f]+) <([^>]+)>:',line)
  if heading:name=heading[2];functions[name]={};continue
  match=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+([^\s]+)\s*(.*)',line)
  if match and name and match[3]!='.byte':
   functions[name][int(match[1],16)]=(match[3],match[4])
 return functions

def minimum_memory_path(ops,start,end):
 addresses=sorted(ops);following=dict(zip(addresses,addresses[1:]))
 heap=[(0,start,[])];seen=set()
 while heap:
  cost,addr,path=heapq.heappop(heap)
  if addr in seen or not start<=addr<=end:continue
  seen.add(addr);op,args=ops[addr];path=path+[addr]
  cost+=int(op.startswith(('l8','l16','l32','s8','s16','s32')))
  if addr==end:return cost,path
  target=re.search(r'\b([0-9a-f]+) <',args)
  if op=='j':destinations=[int(target[1],16)]
  elif op.startswith('b'):destinations=[int(target[1],16),following[addr]]
  elif op.startswith(('ret','loop','call')):
   # Reject unsupported control transfers instead of inventing a path.
   raise ValueError(f'unsupported {op} at {addr:x}')
  else:destinations=[following[addr]]
  for dest in destinations:heapq.heappush(heap,(cost,dest,path))
 raise ValueError('no complete butterfly path')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',default='xtensa-esp32s3-elf-gcc')
 p.add_argument('--core-isa',type=Path,required=True);a=p.parse_args()
 config=a.core_isa.read_text()
 if not re.search(r'#define XCHAL_NUM_LOADSTORE_UNITS\s+1\b',config):raise ValueError('unexpected memory issue configuration')
 if not re.search(r'#define XCHAL_HAVE_CONNXD2_DUALLSFLIX\s+0\b',config):raise ValueError('unexpected dual LS FLIX')
 cc=shutil.which(a.cc) or a.cc;prefix=cc[:-3]
 out=ROOT/'reports/s3-fft-target-bound';out.mkdir(parents=True,exist_ok=True)
 build=ROOT/'build/s3-fft-target-bound';build.mkdir(parents=True,exist_ok=True);obj=build/'fft.o'
 command=[cc,'-O3','-std=c11','-Wall','-Wextra','-Werror','-mlongcalls','-fstack-usage',
  '-c','experiments/s3_fft_tiles.c','-o',str(obj)]
 subprocess.run(command,cwd=ROOT,check=True)
 asm='\n'.join(line.rstrip() for line in subprocess.check_output([prefix+'objdump','-dr',str(obj)],text=True).splitlines())+'\n'
 (out/'fft-O3.disasm').write_text(asm)
 functions=parse(asm);results={}
 for name in ('s3_fft_stage_tile','s3_fft_stage_quarter_tile'):
  ops=functions[name]
  # First backwards jump is the normal span>=2 loop. The subsequent loop
  # in this compiler output is the invalid span==1 path, not used by FFT.
  backedges=[]
  for addr,(op,args) in sorted(ops.items()):
   target=re.search(r'\b([0-9a-f]+) <',args)
   if op=='j' and target and int(target[1],16)<addr:backedges.append((int(target[1],16),addr))
  if len(backedges)!=2:raise ValueError('compiler CFG changed; inspect butterfly loops before reuse')
  start,end=backedges[0];count,path=minimum_memory_path(ops,start,end)
  if sum(ops[x][0]=='s16i' for x in path)!=4:raise ValueError('incomplete butterfly writes')
  issue=count*4096*13
  results[name]=dict(loop_start_hex=f'{start:x}',loop_end_hex=f'{end:x}',
   minimum_scalar_memory_instructions_per_butterfly=count,
   witness_path_hex=[f'{x:x}' for x in path],butterflies=4096*13,
   memory_issue_cycles_lower_bound=issue,
   ideal_two_core_240MHz_us_lower_bound=issue/480,
   T_period_us=1039.5,T_period_capacity_two_core_cycles=480*1039.5,
   selected_O3_object_fails_even_without_RF=issue>480*1039.5)
 result=dict(scope=__doc__,compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0],
  flags=command[1:-4],source_sha256=hashlib.sha256((ROOT/'experiments/s3_fft_tiles.c').read_bytes()).hexdigest(),
  object_sha256=hashlib.sha256(obj.read_bytes()).hexdigest(),
  core_isa_sha256=hashlib.sha256(a.core_isa.read_bytes()).hexdigest(),
  core_isa_source='https://github.com/espressif/esp-idf/blob/v5.5.1/components/xtensa/esp32s3/include/xtensa/config/core-isa.h',
  single_memory_issue_per_core_cycle_basis='One scalar load/store unit, no dual LS FLIX; optimistic one memory instruction per cycle',
  results=results,CPU_WCET_verified=False,receiver_adopted=False)
 (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 if a.core_isa.resolve()!=(out/'core-isa.h').resolve():shutil.copy2(a.core_isa,out/'core-isa.h')
 print(json.dumps({name:{k:v for k,v in value.items() if k!='witness_path_hex'} for name,value in results.items()},indent=2))

if __name__=='__main__':main()

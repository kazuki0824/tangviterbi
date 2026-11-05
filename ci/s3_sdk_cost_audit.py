"""Pinned SDK path accounting. Instruction counts and named waits, not WCET."""
import argparse, gzip, hashlib, io, json, os, re, subprocess
from collections import Counter
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
ROW=re.compile(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(\S+)\s*(.*)$')
class Binary:
 def __init__(self,toolchain,rom=False):
  self.profile=ROOT/'reports/s3-spi-running-guard/sdk-S/image'
  self.raw=(toolchain.parent/'esp32s3_rev0_rom.elf').read_bytes() if rom else gzip.decompress((self.profile/'s3_raw_probe.elf.gz').read_bytes())
  self.sha=hashlib.sha256(self.raw).hexdigest()
  if not rom:assert self.sha==json.loads((self.profile/'result.json').read_text())['ELF_sha256']
  else:assert hashlib.sha256((toolchain.parent/'rom.tar.gz').read_bytes()).hexdigest()=='921f000164a421c7628fbfee55b173384aafaa51883adc65cd27bf9b0af9e9a9'
  self.elf=ELFFile(io.BytesIO(self.raw));self.symbols={s.name:s for s in self.elf.get_section_by_name('.symtab').iter_symbols()}
  self.path=ROOT/('build/rom-cost.elf' if rom else 'build/sdk-cost.elf');self.path.parent.mkdir(exist_ok=True);self.path.write_bytes(self.raw)
  self.tool=str(toolchain/'bin/xtensa-esp-elf-objdump');self.env=dict(os.environ,XTENSA_GNU_CONFIG=str(toolchain/'lib/xtensa_esp32s3.so'))
  self.cache=ROOT/('build/rom-cost-graphs.json' if rom else 'build/sdk-cost-graphs.json')
  self.graphs=json.loads(self.cache.read_text())['graphs'] if self.cache.exists() and json.loads(self.cache.read_text())['sha']==self.sha else {}
 def graph(self,name):
  if name in self.graphs:return {int(k):v for k,v in self.graphs[name].items()}
  sym=self.symbols[name];base=int(sym['st_value']);end=base+int(sym['st_size']);pending=[base];nodes={}
  assert end>base
  lower=int(self.symbols['__'+name+'_aux']['st_value']) if name in ('memcpy','memset') else base
  while pending:
   pc=pending.pop()
   if pc in nodes:continue
   if not lower<=pc<end:raise ValueError((name,'out-of-function edge',hex(pc)))
   dis=subprocess.check_output([self.tool,'-d',f'--start-address={pc}',f'--stop-address={end}',str(self.path)],env=self.env,text=True)
   rows=[m.groups() for line in dis.splitlines() if (m:=ROW.match(line))]
   assert rows and int(rows[0][0],16)==pc
   for address,code,op,args in rows:
    addr=int(address,16)
    if addr in nodes:break
    n=len(code)//2
    if op.startswith('.') or n not in (2,3,4):raise ValueError((name,hex(addr),'invalid reachable decode',op))
    fall=addr+n;edges=[];loop_end=None
    if op.startswith(('ret','break')) or op=='ill':pass
    elif op=='j' or op.startswith('b'):
     match=re.search(r'\b([0-9a-f]+)\s+<',args)
     if not match:raise ValueError((op,args))
     edges=[int(match[1],16)]
     if op!='j':edges.append(fall)
    elif op.startswith('loop'):
     loop_end=int(re.search(r'\b([0-9a-f]+)\s+<',args)[1],16)
     edges=[fall]
     if op!='loop':edges.append(loop_end)
    elif op=='jx':raise ValueError((name,'indirect jump requires explicit target'))
    else:edges=[fall]
    nodes[addr]=dict(op=op,args=args,size=n,edges=edges,loop_end=loop_end)
    if op=='j' or op.startswith(('b','ret','call','loop')) or op=='ill':
     pending.extend(edges);break
  result={pc-base:dict(n,edges=[x-base for x in n['edges']],loop_end=n['loop_end']-base if n['loop_end'] else None) for pc,n in nodes.items()}
  self.graphs[name]={str(k):v for k,v in result.items()}
  self.cache.write_text(json.dumps(dict(sha=self.sha,graphs=self.graphs)))
  return result
 def trace(self,name,choices,loops=None):
  nodes=self.graph(name);pc=0;path=[];uses=Counter();active=[];literals={};calls=[];loops=loops or {};loop_uses=Counter()
  while True:
   if len(path)>100000:raise ValueError('unbounded declared path')
   node=nodes[pc];op=node['op'];args=node['args'];path.append(dict(offset=pc,**node))
   if op=='l32r':
    m=re.match(r'(a\d+),.*\(([0-9a-f]+) <([^>]+)>\)',args)
    if m:literals[m[1]]=m[3]
   elif op.startswith('call'):
    if op.startswith('callx'):target=literals.get(args.strip(),'INDIRECT:'+args.strip())
    else:target=re.search(r'<([^>]+)>',args)[1]
    calls.append(dict(offset=pc,target=target));literals.clear()
   elif not op.startswith(('b','s8','s16','s32','memw','j','ret','loop')):
    dest=args.split(',')[0]
    if dest in literals:del literals[dest]
   edges=node['edges']
   if not edges:
    assert op.startswith('ret'),(name,pc,op)
    break
   if node['loop_end'] is not None:
    count=loops[pc];assert count>0
    active.append([edges[0],node['loop_end'],count]);loop_uses[pc]+=1
   if len(edges)==2:
    options=choices[pc];options=options if isinstance(options,list) else [options]
    if uses[pc]>=len(options):raise ValueError((name,hex(pc),'more branch visits than declared'))
    nxt=options[uses[pc]];uses[pc]+=1;assert nxt in edges,(name,hex(pc),nxt,edges)
   else:nxt=edges[0]
   if active and nxt==active[-1][1]:
    active[-1][2]-=1
    if active[-1][2]:nxt=active[-1][0]
    else:active.pop()
   pc=nxt
  assert set(choices)==set(uses),(name,set(choices)-set(uses))
  assert all(uses[k]==(len(v) if isinstance(v,list) else 1) for k,v in choices.items())
  assert set(loops)==set(loop_uses)
  return dict(function=name,own_instructions=len(path),calls=calls,path=path)

 def acyclic_envelope(self,name):
  """Maximum own instruction count over nonlogging paths in an acyclic CFG.

  Used only for leaves whose callees are invariant on surviving paths. This
  deliberately permits infeasible branch combinations, so it is an envelope,
  not an observed path or a whole-machine WCET.
  """
  g=self.graph(name);active=set();memo={}
  banned=('__assert_func','esp_log','esp_rom_printf','heap_caps_','cfree')
  def target(pc):
   n=g[pc]
   if not n['op'].startswith('call'):return ''
   if not n['op'].startswith('callx'):return re.search(r'<([^>]+)>',n['args'])[1]
   reg=n['args'].strip();at=pc
   while True:
    pred=[k for k,v in g.items() if k+v['size']==at]
    if len(pred)!=1:return 'INDIRECT:'+reg
    at=pred[0];v=g[at]
    if v['op'].startswith('call'):return 'INDIRECT:'+reg
    if v['args'].split(',')[0]==reg:
     m=re.search(r'\(([0-9a-f]+) <([^>]+)>\)',v['args'])
     return m[2] if v['op']=='l32r' and m else 'INDIRECT:'+reg
  def visit(pc):
   if pc in memo:return memo[pc]
   if pc in active:raise ValueError((name,'cyclic envelope requires explicit loop bound',hex(pc)))
   n=g[pc]
   if n['op'] in ('ill','break') or any(target(pc).startswith(t) for t in banned):return None
   if n['loop_end'] is not None:raise ValueError((name,'hardware loop requires explicit bound'))
   if not n['edges']:
    assert n['op'].startswith('ret');return (1,[pc])
   active.add(pc);paths=[p for edge in n['edges'] if (p:=visit(edge)) is not None];active.remove(pc)
   result=None if not paths else (1+max(paths)[0],[pc]+max(paths)[1]);memo[pc]=result;return result
  length,path=visit(0);ch={pc:path[i+1] for i,pc in enumerate(path[:-1]) if len(g[pc]['edges'])==2}
  result=self.trace(name,ch);assert length==result['own_instructions']
  result['kind']='nonlogging acyclic own-instruction envelope';return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--toolchain',type=Path,required=True);ap.add_argument('--inspect',nargs='*');ap.add_argument('--rom',action='store_true');a=ap.parse_args();b=Binary(a.toolchain.resolve(),a.rom)
 if a.inspect:
  for name in a.inspect:
   g=b.graph(name);print(name,'size',b.symbols[name]['st_size'])
   for off,n in sorted(g.items()):
    if len(n['edges'])!=1 or n['op'].startswith(('call','loop')):print(hex(off),n['op'],n['args'],[hex(x) for x in n['edges']])
if __name__=='__main__':main()

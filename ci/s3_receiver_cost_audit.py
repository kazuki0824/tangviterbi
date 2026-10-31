"""Source-bounded SDK instruction envelopes for receiving state transitions.

Counts instructions, not cycles. Loops have explicit source-derived caps;
branch correlations may be discarded, yielding conservative envelopes.
"""
import argparse,functools,hashlib,json,sys
from pathlib import Path
from ci.s3_sdk_cost_audit import Binary,ROOT
sys.setrecursionlimit(10000)

def bounded(binary,name,forced=None,blocked=(),backedges=None,callees=None,entry=0,terminal_edge=None):
 g=binary.graph(name);forced=forced or {};backedges=backedges or {};callees=callees or {};keys=list(backedges);active=set()
 @functools.lru_cache(None)
 def visit(pc,counts):
  state=(pc,counts)
  if pc in blocked:return None
  if state in active:raise ValueError((name,'cycle without bound',pc))
  n=g[pc]
  if n['loop_end'] is not None:raise ValueError((name,'hardware loop needs separate envelope',pc))
  cost=1
  if n['op'].startswith('call'):
   if pc not in callees:raise ValueError((name,'unresolved call',hex(pc),n['args']))
   cost+=callees[pc]
  if not n['edges']:
   if not n['op'].startswith('ret'):return None
   return cost,(pc,)
  active.add(state);paths=[]
  for dst in n['edges']:
   if pc in forced:
    rule=forced[pc]
    wanted=rule if isinstance(rule,int) else rule['edges'][counts[keys.index(tuple(rule['counter']))]]
    if dst!=wanted:continue
   edge=(pc,dst);nextcounts=counts
   if edge in backedges:
    i=keys.index(edge)
    if counts[i]>=backedges[edge]:continue
    nextcounts=tuple(v+(j==i) for j,v in enumerate(counts))
   rest=(0,()) if (pc,dst)==terminal_edge else visit(dst,nextcounts)
   if rest is not None:paths.append((cost+rest[0],(pc,)+rest[1]))
  active.remove(state)
  return max(paths) if paths else None
 result=visit(entry,(0,)*len(keys));assert result is not None,name
 return dict(function=name,entry=entry,terminal_edge=terminal_edge,instructions=result[0],own_instructions=len(result[1]),witness=list(result[1]),forced={hex(k):(hex(v) if isinstance(v,int) else v) for k,v in forced.items()},blocked=[hex(x) for x in blocked],backedge_caps={f'{a:x}->{b:x}':v for (a,b),v in backedges.items()},callee_instructions={hex(k):v for k,v in callees.items()},states=visit.cache_info().currsize)

def audit(tc):
 b=Binary(tc);out={}
 sdk_cost=json.loads((ROOT/'reports/s3-sdk-cost-ledger/results.json').read_text());assert sdk_cost['sdk_elf_sha256']==b.sha
 reset=sdk_cost['roots']['5']['wdt_feed_0']['inclusive_instructions']
 # Clock helper accepts all nonfaulting monotonic common-clock branches,
 # including low-word wrap. Callback body includes its own carry branches.
 out['clock']=bounded(b,'s3_cycle_clock_read',forced={8:0xa,0xd:0xf},blocked=[0x28])
 out['clock_now']=bounded(b,'clock_now',forced={9:0xc},blocked=[0x41],callees={0xe:out['clock']['instructions']})
 for key in ['healthy','mmio_read','mmio_write','mmio_bank','s3_pp_reclaim']:
  out[key]=bounded(b,key)
 out['available']=bounded(b,'available',callees={9:out['s3_pp_reclaim']['instructions']})
 out['pp_accept']=bounded(b,'s3_pp_accept')
 out['accept']=bounded(b,'accept',callees={0x2e:out['pp_accept']['instructions']})
 clock=out['clock_now']['instructions'];bank=out['mmio_bank']['instructions']
 calls={0x24:clock,0x4e:out['healthy']['instructions'],0xf9:bank,0x161:bank,0x18d:bank,0x206:clock,0x223:bank,0x281:out['accept']['instructions'],0x2d8:out['mmio_read']['instructions'],0x33e:out['mmio_write']['instructions'],0x343:clock,0x379:out['available']['instructions'],0x385:out['available']['instructions'],0x412:0,0x476:clock}
 valid={0xd:0x10,0x13:0x16,0x19:0x1c,0x1f:0x22,0x30:0x33,0x59:0x67}
 blocked=[0x61,0x97,0x183,0x28d,0x290,0x306,0x395,0x46d]
 modes={'quiet':{0x88:0x2c1,0x2ef:0x366,0x36a:0x474},
  'prepare':{0x88:0x2c1,0x2ef:0x366,0x36a:0x36d},
  'switch':{0x88:0x2c1,0x2ef:0x2f2},
  'settling':{0x88:0x8b}}
 for key,forced in modes.items():
  out['native_'+key]=bounded(b,'s3_native_poll_budget',forced=valid|forced,blocked=blocked,backedges={(0x141,0x124):11,(0x1c5,0x1a8):11,(0x439,0x3f0):1},callees=calls)
 out['native_settle_wait']=bounded(b,'s3_native_poll_budget',forced=valid|{0x88:0x8b},blocked=blocked+[0xd1],backedges={(0x141,0x124):11,(0x1c5,0x1a8):11,(0x439,0x3f0):1},callees=calls)
 assert out['native_settle_wait']['instructions']<=out['native_quiet']['instructions']
 import itertools
 for owned in range(4):
  variants=[]
  for slots in itertools.combinations(range(3),owned):
   forced={5:8,0x14:0x17,0x22:dict(counter=[0x64,0x1d],edges=[0x24 if i in slots else 0x61 for i in range(3)]),0x6a:0x71 if owned else 0x6c}
   variants.append(bounded(b,'s3_pp_collect',forced=forced,blocked=[0x3c],backedges={(0x64,0x1d):2,(0xee,0x7c):max(0,owned-1)}))
  out['collect_'+str(owned)]=max(variants,key=lambda r:r['instructions'])
 validpack={0x17:0x1a,0x20:0x23,0x33:0x36,0x49:0x4b,0x4b:0x4e,0x78:0x94,0x9a:0x2cc}
 out['pack_empty_impl']=bounded(b,'s3_pp_step_impl',forced=validpack,backedges={(0x97,0x6e):2})
 out['pack_raw_wrapper']=bounded(b,'pack_slice',forced={0x3a:0x50},callees={0x31:0})
 out['pack_empty_quantized']=bounded(b,'s3_pp_step_clocked_quantized',forced={3:0x20},callees={0x23:out['clock']['instructions'],0x47:out['pack_empty_impl']['instructions']})

 out['feed_due']=bounded(b,'feed',forced={0x32:0x34},blocked=[0x1c,0x55],callees={0xf:out['clock']['instructions'],0x50:reset})
 out['feed_normal']=bounded(b,'feed',forced={0x32:0x34},blocked=[0x1c,0x4d],callees={0xf:out['clock']['instructions']})
 task=b.graph('s3_raw_task_entry');empty_calls={p:0 for p,n in task.items() if n['op'].startswith('call')}
 out['owner_shell_with_inline_poll']=bounded(b,'s3_raw_task_entry',entry=0x233,terminal_edge=(0x381,0x233),blocked=[0x25a,0x291,0x28e,0x2c5,0x30d,0x352,0x384],backedges={(0x374,0x2ed):1},callees=empty_calls|{0x281:out['clock']['instructions'],0x37e:out['feed_normal']['instructions']})
 out['worker_shell']=bounded(b,'s3_raw_task_entry',entry=0x419,terminal_edge=(0x438,0x419),blocked=[0x469,0x43b],callees=empty_calls|{0x435:out['feed_normal']['instructions']})
 fill=b.graph('fill$isra$0')
 body=[p for p in fill if 0x40<=p<0x6b or 0x91<=p<0x98]
 assert len(body)==20 and sum(0x40<=p<0x6b for p in body)==17
 out['fill_formula']=dict(nonbody_per_span=len(fill)-len(body),bank_callback=out['mmio_bank']['instructions'],block8=17,remainder_word=3,source_bound='n<=1024, at masked to 16383; at most two spans. Charge nonbody once per span (overapprox), bank callback once per invocation.')
 return out

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--toolchain',type=Path,required=True);a=ap.parse_args()
 out=ROOT/'reports/s3-receiver-cost-ledger';out.mkdir(exist_ok=True)
 result=dict(paths=audit(a.toolchain.resolve()),hardware_wcet=False,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'ci/s3_sdk_cost_audit.py',ROOT/'experiments/s3_native_capture.c',ROOT/'experiments/s3_raw_tasks.c',ROOT/'experiments/s3_parallel_pack.c',ROOT/'reports/s3-sdk-cost-ledger/results.json']})
 (out/'instructions.json').write_text(json.dumps(result,indent=2)+'\n')
 print({k:v.get('instructions',v) for k,v in result['paths'].items()})
if __name__=='__main__':main()

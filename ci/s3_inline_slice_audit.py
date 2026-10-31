"""Whole-slice instruction envelope for the N16R8 inline packing candidate."""
import argparse,hashlib,json,math
from pathlib import Path
from ci.s3_queue_cost_audit import candidate
from ci.s3_sdk_cost_audit import ROOT
from ci.s3_receiver_cost_audit import bounded

def audit(tc):
 b=candidate(tc);g=b.graph('s3_pp_step_impl');w=b.graph('s3_pp_step_clocked_quantized')
 bulk={p for p in g if 0x1b8<=p<0x220}
 byte={p for p in g if 0x27e<=p<0x29c}
 scan={p for p in g if 0x70<=p<0x9e}
 body={p for p in g if 0xf9<=p<0x2a6 or 0x348<=p<0x378}
 regular=body-bulk-byte;once=set(g)-body
 assert (len(bulk),len(byte),len(scan))==(39,11,18)
 assert g[0x1b5]['loop_end']==0x220 and g[0x1b5]['edges']==[0x1b8]
 loops={(0x9b,0x70),(0x298,0x27e),(0x2a3,0xf9)}
 assert all(dst in g[src]['edges'] for src,dst in loops)
 active=set();done=set()
 def walk(pc):
  assert pc not in active,('unbounded loop',hex(pc))
  if pc in done:return
  active.add(pc)
  for dst in g[pc]['edges']:
   if (pc,dst) not in loops:walk(dst)
  active.remove(pc);done.add(pc)
 walk(0);assert done==set(g)
 assert len([p for p,n in g.items() if n['op'].startswith('call')])==1 and g[0x2ce]['op']=='callx8'
 assert not body&scan and bulk|byte<=body
 coeff=dict(block=len(bulk),run=len(regular),slow_pair=len(regular)+5*len(byte),slice=len(once)+2*len(scan)+len(w))
 empty=bounded(b,'s3_pp_step_impl',forced={0x19:0x1c,0x22:0x25,0x33:0x36,0x49:0x4b,0x4b:0x4e,0x7c:0x98,0x9e:0x342},backedges={(0x9b,0x70):2})
 empty_wrapper=bounded(b,'s3_pp_step_clocked_quantized',forced={3:0x20},callees={0x23:21,0x47:empty['instructions']})
 # Inherited receiver clock and pack_slice wrapper costs, still separate.
 instructions=dict(PACK_BLOCK=coeff['block'],PACK_RUN=coeff['run'],PACK_SLOW=coeff['slow_pair'],PACK_SLICE=coeff['slice']+21*2+25,PACK_EMPTY=empty_wrapper['instructions']+25)
 return dict(ELF_sha256=b.sha,coefficients=coeff,instructions=instructions,fees_cycles={k:math.ceil(v*1.1) for k,v in instructions.items()},empty_impl=empty,empty_wrapper=empty_wrapper,regions={k:sorted(v) for k,v in dict(bulk=bulk,byte=byte,scan=scan,regular=regular,once=once).items()},scope='All CFG nodes partitioned; scan <=3, byte loop <=5 per slow pair, hardware bulk loop once per 8 samples. Clock=21 and raw wrapper=25 instructions inherited; register-window traps and stalls not bounded.',hardware_wcet=False,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'ci/s3_queue_cost_audit.py',ROOT/'ci/s3_receiver_cost_audit.py',ROOT/'reports/s3-queue-study/sdk-n16r8/s3_queue_probe.elf.gz',ROOT/'experiments/s3_inline_pack.c',ROOT/'experiments/s3_iq10_inline.h',ROOT/'experiments/s3_parallel_pack.c',ROOT/'reports/s3-receiver-cost-ledger/instructions.json']})

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--toolchain',type=Path,required=True);a=ap.parse_args()
 r=audit(a.toolchain.resolve());(ROOT/'reports/s3-inline-packing/slice-costs.json').write_text(json.dumps(r,indent=2)+'\n');print(r['coefficients']);print(r['fees_cycles'])

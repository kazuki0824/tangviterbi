"""Declared nonnested level-1 IRQ assembly path; window traps separate."""
import argparse,hashlib,json,re,subprocess
from collections import Counter
from pathlib import Path
from ci.s3_sdk_cost_audit import Binary,ROOT,ROW

def trace(b,name,choices=None,stop_offset=None,stop_target=None):
 base=int(b.symbols[name]['st_value']);pc=base;choices=choices or {};used=Counter();path=[];calls=[];decoded={}
 while True:
  if pc not in decoded:
   dis=subprocess.check_output([b.tool,'-d',f'--start-address={pc}',f'--stop-address={pc+256}',str(b.path)],env=b.env,text=True)
   # Only use the current basic block. Never trust disassembly through padding.
   for line in dis.splitlines():
    m=ROW.match(line)
    if not m:continue
    addr=int(m[1],16);op=m[3];args=m[4];size=len(m[2])//2
    decoded[addr]=(op,args,size)
    if op.startswith(('b','ret','call','rf')) or op in ('j','jx'):break
  op,args,size=decoded[pc];offset=pc-base;path.append(dict(offset=offset,op=op,args=args))
  assert not op.startswith('.') and op!='ill'
  if op.startswith('call'):calls.append(dict(offset=offset,target=re.search(r'<([^>]+)>',args)[1] if not op.startswith('callx') else 'handler'))
  if offset==stop_offset or op.startswith(('ret','rf')):break
  if op=='j' or op.startswith('b'):
   target=int(re.search(r'\b([0-9a-f]+)\s+<',args)[1],16)
   if op=='j':nxt=target
   else:
    selected=choices[offset];selected=selected if isinstance(selected,list) else [selected]
    nxt=base+selected[used[offset]];used[offset]+=1;assert nxt in (target,pc+size)
   if stop_target is not None and nxt==int(b.symbols[stop_target]['st_value']):break
   pc=nxt
  elif op=='jx':raise ValueError('undeclared indirect jump')
  else:pc+=size
  assert len(path)<1000
 assert set(used)==set(choices)
 assert all(used[k]==(len(v) if isinstance(v,list) else 1) for k,v in choices.items())
 return dict(function=name,own_instructions=len(path),path=path,calls=calls)

def audit(tc):
 b=Binary(tc);out={}
 for name in ['xthal_save_extra_nw','xthal_restore_extra_nw','_xt_context_restore','_xt_user_exit']:
  out[name]=trace(b,name)
 out['_xt_context_save']=trace(b,'_xt_context_save',{0x52:0x55})
 out['_frxt_int_enter']=trace(b,'_frxt_int_enter',{0x1e:0x20,0x26:0x29,0x31:0x33})
 out['_frxt_int_exit']=trace(b,'_frxt_int_exit',{0x17:0x19,0x1f:0x21,0x29:0x2b,0x35:0x49})
 out['_xt_lowint1']=trace(b,'_xt_lowint1',{0x41:[0x44,0x94],0x62:0x65},stop_offset=0x97)
 out['_xt_user_exc']=trace(b,'_xt_user_exc',{3:6},stop_target='_xt_lowint1')
 out['_UserExceptionVector']=trace(b,'_UserExceptionVector',stop_offset=3)
 out['vPortYieldFromInt']=trace(b,'vPortYieldFromInt')
 out['_frxt_dispatch']=trace(b,'_frxt_dispatch',{0x1a:0x2d})
 out['_frxt_int_exit_switch']=trace(b,'_frxt_int_exit',{0x17:0x19,0x1f:0x21,0x29:0x2b,0x35:0x37},stop_offset=0x46)
 scheduler=json.loads((ROOT/'reports/s3-receiver-cost-ledger/tick.json').read_text())['paths']['scheduler_same_task']['instructions']
 def close(name):
  if name=='vTaskSwitchContext':return scheduler
  r=out[name]
  return r['own_instructions']+sum(close(c['target']) for c in r['calls'] if c['target']!='handler')
 # ret from frxt_exit restores the exception-frame return address, user_exit.
 windows={n:trace(b,n) for n in ['_WindowOverflow4','_WindowOverflow8','_WindowOverflow12','_WindowUnderflow4','_WindowUnderflow8','_WindowUnderflow12']}
 total=close('_UserExceptionVector')+close('_xt_lowint1')+close('_xt_user_exit')
 switched=total-close('_frxt_int_exit')+close('_frxt_int_exit_switch')
 return dict(switch_instructions_excluding_handler_and_window_traps=switched,scheduler_instructions=scheduler,paths=out,window_trap_paths=windows,instructions_excluding_handler_and_window_traps=total,conditions=['One pending level-1 source, nonnested, scheduler running, current task exists, no requested context switch.','C handler body is charged separately; exception frame returns through _xt_user_exit.','Window overflow/underflow traps during context save or C calls are not folded into this count.'],source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'ci/s3_sdk_cost_audit.py',ROOT/'reports/s3-receiver-cost-ledger/tick.json']},hardware_wcet=False)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--toolchain',type=Path,required=True);a=ap.parse_args();r=audit(a.toolchain.resolve());p=ROOT/'reports/s3-receiver-cost-ledger/irq-entry.json';p.write_text(json.dumps(r,indent=2)+'\n');print(r['instructions_excluding_handler_and_window_traps'])

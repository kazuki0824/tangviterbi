"""Cost-driven actual C state transitions; numerical scenarios, not target WCET."""
import argparse, hashlib, json, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CATEGORIES=['OWNER_SHELL','WORKER_SHELL','PACK_EMPTY','PACK_SLICE','PACK_RUN','PACK_BLOCK','PACK_SLOW','RF_BASE','RF_PREPARE','RF_SWITCH','RF_ACCEPT','FILL','COLLECT','SUBMIT_EMPTY','SUBMIT_DONE','REAP_RUNNING','REAP_DONE','SPI_IRQ','TICK_IRQ','WDT']
FIXED_COSTS = dict(OWNER_SHELL=154, WORKER_SHELL=88, PACK_EMPTY=180,
 PACK_SLICE=306, PACK_RUN=130, PACK_BLOCK=50, PACK_SLOW=191,
 RF_BASE=208, RF_PREPARE=220, RF_SWITCH=142, RF_ACCEPT=992,
 SUBMIT_EMPTY=120, SUBMIT_DONE=4000, REAP_DONE=800, WDT=800)
def replace(text, old, new):
 if text.count(old)!=1: raise ValueError('instrumentation source changed: '+old)
 return text.replace(old,new)
def function(text,name):
 start=text.index('static bool IRAM_ATTR '+name+'(');brace=text.index('{',start);depth=1;i=brace+1
 while depth:
  depth+=(text[i]=='{')-(text[i]=='}');i+=1
 return text[start:i]
def generated():
 pack=(ROOT/'experiments/s3_parallel_pack.c').read_text()
 edits=[
 (' if(now>=b->deadline || bound>=b->deadline-now)return fail(p,S3_PP_DEADLINE);', ' if(now>=b->deadline || bound>=b->deadline-now){joint_failed_admission(b->deadline,now);return fail(p,S3_PP_DEADLINE); }'),
 ('  uint64_t finished=clock(clock_ctx);','  uint64_t finished=clock(clock_ctx);joint_pack_interval(finished-now);'),
 (' if(!b)return S3_PP_EMPTY;', ' if(!b){joint_charge(PACK_EMPTY,180);return S3_PP_EMPTY;}\n joint_charge(PACK_SLICE,306);'),
 ('   const uint32_t *src=b->words+input;', '   joint_charge(PACK_RUN,130);\n   const uint32_t *src=b->words+input;'),
 ('    pack_eight(dst,src);', '    joint_charge(PACK_BLOCK,50);pack_eight(dst,src);'),
 ('   uint32_t a=word(b,logical),c=word(b,logical+1);', '   joint_charge(PACK_SLOW,191);\n   uint32_t a=word(b,logical),c=word(b,logical+1);'),
 (' if(j->cursor==j->end)atomic_store_explicit', ' joint_deadline(b->deadline);\n if(j->cursor==j->end)atomic_store_explicit'),
 (' p->next_sample+=count;p->reserved+=bytes;', ' p->next_sample+=count;p->reserved+=bytes;joint_accept(bank);'),
 ('  b->owned=false;p->head=', '  joint_publish(p->fifo[p->head]);b->owned=false;p->head='),
 ('int HOT s3_pp_collect(s3_parallel_pack *p,uint64_t now) {', 'int HOT s3_pp_collect(s3_parallel_pack *p,uint64_t now) {\n joint_charge(COLLECT,35+160*p->count);')]
 for old,new in edits:pack=replace(pack,old,new)
 native=(ROOT/'experiments/s3_native_capture.c').read_text()
 for old,new in [
 (' volatile uint32_t *p=s->io.bank(s->io.ctx,b);',' joint_charge(FILL,(17124ULL*n+7167)/7168);\n volatile uint32_t *p=s->io.bank(s->io.ctx,b);'),
 (' if(!s||!prepare_words||!s->running||s->fault)return false;', ' if(!s||!prepare_words||!s->running||s->fault)return false;\n joint_charge(RF_BASE,208);'),
 ('  unsigned f=first(s,b,', '  joint_charge(RF_ACCEPT,992);\n  unsigned f=first(s,b,'),
 ('  s->switch_earliest=now-s->clock_error;', '  joint_charge(RF_SWITCH,142);\n  s->switch_earliest=now-s->clock_error;'),
 (' if(!s->prepared){', ' if(!s->prepared){\n  joint_charge(RF_PREPARE,220);')]:native=replace(native,old,new)
 for category,cost in FIXED_COSTS.items():
  pack=pack.replace(f'joint_charge({category},{cost})',f'joint_charge({category},COST_{category})')
  native=native.replace(f'joint_charge({category},{cost})',f'joint_charge({category},COST_{category})')
 return {'pack.c':'#include "joint_costs.h"\n'+pack,'native.c':'#include "joint_costs.h"\n'+native,
 'joint_owner.inc':function((ROOT/'experiments/s3_raw_tasks.c').read_text(),'owner_iteration'),
 'joint_costs.h':'#include <stdint.h>\n'+''.join(f'#define COST_{k} {v}\n' for k,v in FIXED_COSTS.items())+'enum {'+','.join(CATEGORIES)+',CATEGORIES};\nvoid joint_charge(unsigned,uint64_t);\nvoid joint_accept(unsigned);\nvoid joint_publish(unsigned);\nvoid joint_deadline(uint64_t);\nvoid joint_failed_admission(uint64_t,uint64_t);\nvoid joint_pack_interval(uint64_t);\n'}
def run(cases):
 cases=[tuple(c)+(20000,) if len(c)==6 else tuple(c) for c in cases]
 generated_files=generated();rows=[]
 with tempfile.TemporaryDirectory() as tmp:
  tmp=Path(tmp)
  for name,text in generated_files.items():(tmp/name).write_text(text)
  for rate,share,chunk in sorted(set((c[0],c[1],32768 if c[0]==16 else 16384) for c in cases)):
   binary=tmp/f'probe-{rate}-{share}'
   subprocess.run(['cc','-std=c11','-O2','-g','-Wall','-Wextra','-Wno-misleading-indentation','-fsanitize=undefined','-fno-sanitize-recover=all','-ffunction-sections','-Wl,--gc-sections',f'-DS3_PP_CORE0_SIXTEENTHS={share}',f'-DS3_RAW_TRANSFER_BYTES={chunk}',f'-I{tmp}',f'-I{ROOT / "experiments"}',str(ROOT/'experiments/s3_joint_runtime.c'),str(tmp/'pack.c'),str(tmp/'native.c'),str(ROOT/'experiments/s3_parallel_capture.c'),'-o',str(binary)],check=True)
   for r,sh,sl,n,irq,stall,bound in cases:
    if (r,sh)!=(rate,share):continue
    row=json.loads(subprocess.check_output([str(binary),str(r),str(sl),str(n),str(irq),str(stall),str(bound)],text=True))
    row['requested_banks']=n;row['scenario_pass']=row['banks']==n and not any(row[k] for k in ('native_fault','pack_fault','task_fault','outcome'))
    row['cost_ledger']=[{key:{'events':v[0],'cycles':v[1],'events_s':v[0]*240e6/row['cycles'],'cpu_percent':v[1]*100/row['cycles']} for key,v in zip(CATEGORIES,core)} for core in row.pop('costs')]
    # Pending operations can extend beyond the stopped observation window.
    row['elapsed_accounting_identity']=[row['charged_cycles'][c]+row['stall_cycles'][c]==row['accounted_until_cycles'][c] for c in (0,1)]
    row['pending_cycles']=[row['accounted_until_cycles'][c]-row['cycles'] for c in (0,1)]
    row['accounting_identity']=[sum(x['cycles'] for x in row['cost_ledger'][c].values())==row['charged_cycles'][c] for c in (0,1)]
    rows.append(row)
 return {'scope':__doc__,'rows':rows,'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'experiments'/n for n in ('s3_joint_runtime.c','s3_joint_runtime.py','s3_raw_tasks.c','s3_native_capture.c','s3_parallel_pack.c','s3_parallel_capture.c')]},'generated_sha256':{n:hashlib.sha256(t.encode()).hexdigest() for n,t in generated_files.items()},'hardware_proven':False,'receiver_adopted':False,'fixed_cost_cycles':FIXED_COSTS,'dynamic_costs':{'FILL':'ceil(17124*words/7168)', 'COLLECT':'35+160*owned_banks', 'REAP_RUNNING':[42,44], 'SPI_IRQ':'irq_cycles, two entries/transfer in this scenario', 'TICK_IRQ':'2000 each core, 100Hz', 'stall':'ceil(base_operation_cycles*stall_percent/100), excludes asynchronous IRQ extensions'},'scope_limits':['Fixed costs mix alpha=1.1 instruction envelopes and unmeasured allocated budgets; none are target WCET.', 'Only reception loop is timed; startup/shutdown/fault handling and other application/PHY tasks are outside the model.', '10,000/20,000 cycle slice admission bounds are assumptions, not measured bounds.', 'Ideal RF ABI and exact common clock; 80MHz SPI with immediate SDK publication after completion IRQ.', 'Operation cost placement is a discretization, not instruction-level interleaving; fixed core0 priority for simultaneous events.', 'No inherited U, differential scans, or separate API20us term is added. Costs are charged once at the named boundary.']}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--banks',type=int,default=100);ap.add_argument('--output',type=Path,default=ROOT/'reports/s3-joint-runtime/results.json');args=ap.parse_args()
 cases=[(r,sh,sl,args.banks,irq,st) for r,sh in [(16,8),(40,6),(40,5)] for sl in (256,512) for irq,st in [(300,0),(1000,0),(300,10)]]
 cases += [(40,6,256,100,300,0,10000),(40,6,512,100,300,0,10000),(16,8,512,4000,300,0),(16,8,512,100,30000,0)]
 result=run(cases);args.output.parent.mkdir(exist_ok=True,parents=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
 for row in result['rows']:print({k:row[k] for k in ('rate','share','slice_pairs','irq_cycles','stall_percent','banks','scenario_pass','native_fault','pack_fault','outcome','max_rf_poll_gap','peak_arena_bytes')})

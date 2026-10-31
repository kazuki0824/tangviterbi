"""Observe wire-idle causes without changing virtual execution costs or order."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
from experiments.s3_joint_runtime import ROOT,generated,replace
from experiments.s3_owner_order_estimate import owner_variant
LABELS=['wire_busy','launch_in_progress','published_wait','collect_wait','packing_wait']
def instrument():
 s=(ROOT/'experiments/s3_joint_runtime.c').read_text()
 s=replace(s,'static unsigned launches[2];','static unsigned launches[2],launch_pending[2];\nstatic uint64_t tx_states[2][5],queued_opportunity[2];')
 s=replace(s,' assert(t>=now);',''' assert(t>=now);
 if(started){
  bool published=pack.submitted<pack.published/S3_PP_TX_BYTES;
  bool collectable=false;
  if(pack.count){s3_pp_bank*b=&pack.banks[pack.fifo[pack.head]];
   collectable=atomic_load(&b->jobs[0].state)==2 && atomic_load(&b->jobs[1].state)==2;}
  for(unsigned h=0;h<2;h++){
   bool busy=launches[h]&&now<wire_done[h];
   unsigned state=busy?0:launch_pending[h]?1:published?2:collectable?3:4;
   tx_states[h][state]+=t-now;
   if(busy&&published)queued_opportunity[h]+=t-now;
  }
 }''')
 s=replace(s,' joint_charge(SUBMIT_DONE,COST_SUBMIT_DONE);',' launch_pending[h]=1;\n joint_charge(SUBMIT_DONE,COST_SUBMIT_DONE);')
 s=replace(s,' wire_done[h]=now+wire;irq_at[h]=wire_done[h];',' wire_done[h]=now+wire;irq_at[h]=wire_done[h];launch_pending[h]=0;')
 s=replace(s,' printf("\\\"prepare_per_iteration\\\":%u,\\\"prepare_per_poll\\\":%u,",prepare_per_iteration,prepare_per_poll);',''' printf("\\\"tx_state_cycles\\\":[");
 for(unsigned h=0;h<2;h++){printf("%s[",h?",":"");for(unsigned k=0;k<5;k++)printf("%s%llu",k?",":"",(unsigned long long)tx_states[h][k]);printf("]");}printf("],\\\"queued_opportunity_cycles\\\":[%llu,%llu],",(unsigned long long)queued_opportunity[0],(unsigned long long)queued_opportunity[1]);
 printf("\\\"prepare_per_iteration\\\":%u,\\\"prepare_per_poll\\\":%u,",prepare_per_iteration,prepare_per_poll);''')
 return s

def main():
 source=ROOT/'reports/s3-counter-envelope/runtime.json';base=json.loads(source.read_text());rows=[]
 with tempfile.TemporaryDirectory() as td:
  td=Path(td);c=instrument();(td/'observer.c').write_text(c)
  for rate,share,order in [(16,8,'PCAB'),(40,5,'PCAB'),(40,5,'BCPA'),(40,6,'PCAB'),(40,6,'BCPA')]:
   profile=next(p for p in base['profiles'] if p['order']==order and (p['rows'][0]['rate'],p['rows'][0]['share'])==(rate,share))
   files=generated(profile['fixed_cost_cycles']);files['joint_owner.inc']=owner_variant(order)
   for n,s in files.items():(td/n).write_text(s)
   binary=td/'probe';chunk=32768 if rate==16 else 16384
   subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Wno-misleading-indentation','-fsanitize=undefined','-fno-sanitize-recover=all','-ffunction-sections','-Wl,--gc-sections',f'-DS3_PP_CORE0_SIXTEENTHS={share}',f'-DS3_RAW_TRANSFER_BYTES={chunk}',f'-I{td}',f'-I{ROOT/"experiments"}',str(td/'observer.c'),str(td/'pack.c'),str(td/'native.c'),str(ROOT/'experiments/s3_parallel_capture.c'),'-o',str(binary)],check=True)
   reference=next(r for r in reversed(profile['rows']) if r['prepare_per_iteration']==2048)
   r=json.loads(subprocess.check_output([str(binary),str(rate),'512',str(reference['requested_banks']),'1','0','20000','2048','1024'],text=True))
   for key,value in r.items():
    if key in reference:assert value==reference[key],(key,value,reference[key])
   for h in (0,1):assert sum(r['tx_state_cycles'][h])==r['cycles']
   r['order']=order;r['reference_banks']=reference['requested_banks'];rows.append(r)
 out=ROOT/'reports/s3-tx-idle-study';out.mkdir(exist_ok=True)
 result={'rows':rows,'labels':LABELS,'diagnostic_only':True,'unchanged_reference_fields_checked':True,'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),source,ROOT/'experiments/s3_joint_runtime.c',ROOT/'experiments/s3_joint_runtime.py',ROOT/'experiments/s3_owner_order_estimate.py']},'instrumented_c_sha256':hashlib.sha256(c.encode()).hexdigest()}
 (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 for r in rows:
  print(r['rate'],r['share'],r['order'],r['banks'],[[round(100*v/r['cycles'],3) for v in port] for port in r['tx_state_cycles']],flush=True)
if __name__=='__main__':main()

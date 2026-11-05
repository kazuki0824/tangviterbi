"""Search declared packing/preparation settings against periodic service; no measured WCET."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
from experiments.s3_joint_runtime import ROOT,generated,replace,CATEGORIES
from experiments.s3_queue_owner_runtime import owner_body
from experiments.s3_queue_timer_core1_runtime import source
OUT=ROOT/'reports/s3-queue-owner'
def main():
 reference=next(r for r in json.loads((OUT/'runtime.json').read_text())['rows'] if r['requested_banks']==20000)
 costs=reference['costs_used'];categories=CATEGORIES+['PHY_TIMER'];rows=[]
 with tempfile.TemporaryDirectory() as td:
  td=Path(td);files=generated(costs);files['joint_owner.inc']=owner_body()
  files['joint_costs.h']=replace(files['joint_costs.h'],',CATEGORIES};',',PHY_TIMER,CATEGORIES};')
  files['pack.c']=replace(files['pack.c'],'#include "s3_iq10_block.h"','#include "s3_iq10_inline.h"');files['queue.c']=source()
  for n,s in files.items():(td/n).write_text(s)
  for share in (5,6):
   exe=td/f'probe-{share}';subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Wno-misleading-indentation','-fsanitize=undefined','-fno-sanitize-recover=all','-ffunction-sections','-Wl,--gc-sections',f'-DS3_PP_CORE0_SIXTEENTHS={share}','-DS3_RAW_TRANSFER_BYTES=16384',f'-I{td}',f'-I{ROOT/"experiments"}',f'-I{ROOT/"tests/s3_sdk_shim"}',str(td/'queue.c'),str(td/'pack.c'),str(td/'native.c'),str(ROOT/'experiments/s3_parallel_capture.c'),str(ROOT/'experiments/s3_raw_queue.c'),'-o',str(exe)],check=True)
   for sl in (128,256,512):
    for prep in (2048,3072,4096):
     for fee in (12000,24000):
      passed=True
      for phase,count in [(p,4000) for p in (1,60000000,120000000,180000000,240000000)]+[(120000000,20000)]:
       r=json.loads(subprocess.check_output([str(exe),'40',str(sl),str(count),'1','0','40000',str(prep),'1024',str(fee),str(phase)],text=True))
       r.update(requested_banks=count,periodic_service_cycles=fee,first_release_cycles=phase,period_cycles=240000000,service_core=1)
       r['scenario_pass']=r['banks']==count and not any(r[k] for k in ('native_fault','pack_fault','task_fault','outcome'))
       r['cost_ledger']=[{key:{'events':v[0],'cycles':v[1]} for key,v in zip(categories,core)} for core in r.pop('costs')]
       for c in (0,1):assert sum(v['cycles'] for v in r['cost_ledger'][c].values())==r['charged_cycles'][c] and r['charged_cycles'][c]+r['stall_cycles'][c]==r['accounted_until_cycles'][c]
       rows.append(r);print(share,sl,prep,fee,phase,count,r['banks'],r['scenario_pass'],flush=True)
       if not r['scenario_pass']:passed=False;break
      if not passed:break
 result=dict(scope=__doc__,rows=rows,all_SoC_costs_finalized=False,SDK_candidate_settings_built=False,service_budget_measured=False,
  search_rule='18 settings: share5/6, slice128/256/512, preparation2048/3072/4096. Core1 periodic service50us then100us. Reject on first sampled failure. Each surviving setting tested at five phases/4000 banks then half-period/20000 banks. Slice bound40000 is conditional, not measured.',
  limitations=['Whole timer service placed on core1; actual timer IRQ/task split, other timer activity and PHY RF effects unresolved.', 'Compiled owner control fees inherited from 2048-word/512-sample candidate; target recount required before adopting changed settings.', 'Early rejection avoids spending time testing further phases of a setting already known to fail; no all-phase proof.'],
  source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'experiments/s3_queue_timer_core1_runtime.py',ROOT/'experiments/s3_queue_periodic_runtime.py',OUT/'runtime.json']})
 (OUT/'periodic-candidates.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()

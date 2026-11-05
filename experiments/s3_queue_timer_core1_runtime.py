"""Compare placing one-Hz service on worker core1 with an explicit slice bound."""
import hashlib,json,subprocess,tempfile
from pathlib import Path
from experiments.s3_joint_runtime import ROOT,generated,replace,CATEGORIES
from experiments.s3_queue_owner_runtime import owner_body
from experiments.s3_queue_periodic_runtime import source as core0_source
OUT=ROOT/'reports/s3-queue-owner'
def source():
 s=core0_source()
 for a in ('ready[0]+=phy_cycles','charged[0][PHY_TIMER]','counts[0][PHY_TIMER]','interrupts[0]+=phy_cycles'):s=replace(s,a,a.replace('[0]','[1]'))
 return s

def main():
 reference=next(r for r in json.loads((OUT/'runtime.json').read_text())['rows'] if r['requested_banks']==20000)
 costs=reference['costs_used'];categories=CATEGORIES+['PHY_TIMER'];rows=[]
 with tempfile.TemporaryDirectory() as td:
  td=Path(td);files=generated(costs);files['joint_owner.inc']=owner_body()
  files['joint_costs.h']=replace(files['joint_costs.h'],',CATEGORIES};',',PHY_TIMER,CATEGORIES};')
  files['pack.c']=replace(files['pack.c'],'#include "s3_iq10_block.h"','#include "s3_iq10_inline.h"');files['queue.c']=source()
  for n,s in files.items():(td/n).write_text(s)
  exe=td/'probe';subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Wno-misleading-indentation','-fsanitize=undefined','-fno-sanitize-recover=all','-ffunction-sections','-Wl,--gc-sections','-DS3_PP_CORE0_SIXTEENTHS=5','-DS3_RAW_TRANSFER_BYTES=16384',f'-I{td}',f'-I{ROOT/"experiments"}',f'-I{ROOT/"tests/s3_sdk_shim"}',str(td/'queue.c'),str(td/'pack.c'),str(td/'native.c'),str(ROOT/'experiments/s3_parallel_capture.c'),str(ROOT/'experiments/s3_raw_queue.c'),'-o',str(exe)],check=True)
  for fee in (12000,24000,48000,120000):
   for bound in (20000,40000):
    phases=(1,60000000,120000000,180000000,240000000);passed=True
    for phase,count in [(p,4000) for p in phases]+[(120000000,20000)]:
     if count==20000 and not passed:continue
     r=json.loads(subprocess.check_output([str(exe),'40','512',str(count),'1','0',str(bound),'2048','1024',str(fee),str(phase)],text=True))
     r.update(requested_banks=count,periodic_service_cycles=fee,first_release_cycles=phase,period_cycles=240000000,service_core=1)
     r['scenario_pass']=r['banks']==count and not any(r[k] for k in ('native_fault','pack_fault','task_fault','outcome'));passed &= r['scenario_pass']
     r['cost_ledger']=[{key:{'events':v[0],'cycles':v[1]} for key,v in zip(categories,core)} for core in r.pop('costs')]
     for c in (0,1):assert sum(v['cycles'] for v in r['cost_ledger'][c].values())==r['charged_cycles'][c] and r['charged_cycles'][c]+r['stall_cycles'][c]==r['accounted_until_cycles'][c]
     assert r['cost_ledger'][1]['PHY_TIMER']['cycles']==r['cost_ledger'][1]['PHY_TIMER']['events']*fee
     rows.append(r);print(fee,bound,phase,count,r['banks'],r['scenario_pass'],flush=True)
 r=dict(scope=__doc__,rows=rows,SDK_affinity_changed=False,service_budget_measured=False,all_SoC_costs_finalized=False,
  assumptions=['Same cost model, moving the entire symbolic service budget from core0 to core1; actual timer IRQ/task split and PHY RF effects are not resolved.', '40000-cycle slice admission bound is a declared sensitivity setting, not a measured guarantee; applied to both cores by existing model.', 'Five phases at 4000 banks; only all-passing configurations extended to 20000 banks at half-period phase.'],
  source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'experiments/s3_queue_periodic_runtime.py',ROOT/'experiments/s3_joint_runtime.py',ROOT/'experiments/s3_queue_owner_runtime.py',OUT/'runtime.json']})
 (OUT/'timer-core1-runtime.json').write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()

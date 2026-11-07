"""One-Hz core0 service sensitivity; service budget is NOT a measured PHY cost."""
import json,subprocess,tempfile,hashlib
from pathlib import Path
from experiments.s3_joint_runtime import ROOT,generated,replace,CATEGORIES
from experiments.s3_queue_audited_runtime import audited_source
from experiments.s3_queue_owner_runtime import owner_body
OUT=ROOT/'reports/s3-queue-owner'
def source():
 s=audited_source()
 s=replace(s,'assert(argc==9);','assert(argc==11);phy_cycles=strtoull(argv[9],0,10);next_phy=strtoull(argv[10],0,10);assert(next_phy&&next_phy<=240000000);')
 s=replace(s,'uint64_t event=next_tick;','uint64_t event=next_tick;if(next_phy<event)event=next_phy;')
 s=replace(s,'if(event==next_tick){','if(event==next_phy){ready[0]+=phy_cycles;charged[0][PHY_TIMER]+=phy_cycles;counts[0][PHY_TIMER]++;interrupts[0]+=phy_cycles;next_phy+=240000000;}\n   if(event==next_tick){')
 return 'static unsigned long long phy_cycles,next_phy;\n'+s

def main():
 base=json.loads((OUT/'runtime.json').read_text());reference=next(r for r in base['rows'] if r['requested_banks']==20000)
 costs=reference['costs_used'];categories=CATEGORIES+['PHY_TIMER'];rows=[]
 with tempfile.TemporaryDirectory() as td:
  td=Path(td);files=generated(costs);files['joint_owner.inc']=owner_body()
  files['joint_costs.h']=replace(files['joint_costs.h'],',CATEGORIES};',',PHY_TIMER,CATEGORIES};')
  files['pack.c']=replace(files['pack.c'],'#include "s3_iq10_block.h"','#include "s3_iq10_inline.h"')
  files['queue.c']=source()
  for n,s in files.items():(td/n).write_text(s)
  exe=td/'probe';subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Wno-misleading-indentation','-fsanitize=undefined','-fno-sanitize-recover=all','-ffunction-sections','-Wl,--gc-sections','-DS3_PP_CORE0_SIXTEENTHS=5','-DS3_RAW_TRANSFER_BYTES=16384',f'-I{td}',f'-I{ROOT/"experiments"}',f'-I{ROOT/"tests/s3_sdk_shim"}',str(td/'queue.c'),str(td/'pack.c'),str(td/'native.c'),str(ROOT/'experiments/s3_parallel_capture.c'),str(ROOT/'experiments/s3_raw_queue.c'),'-o',str(exe)],check=True)
  for fee in (0,2400,12000,24000,48000,120000,240000):
   for phase in (1,60000000,120000000,180000000,240000000):
    r=json.loads(subprocess.check_output([str(exe),'40','512','20000','1','0','20000','2048','1024',str(fee),str(phase)],text=True))
    r.update(requested_banks=20000,periodic_service_cycles=fee,first_release_cycles=phase,period_cycles=240000000)
    r['scenario_pass']=r['banks']==20000 and not any(r[k] for k in ('native_fault','pack_fault','task_fault','outcome'))
    r['cost_ledger']=[{key:{'events':v[0],'cycles':v[1]} for key,v in zip(categories,core)} for core in r.pop('costs')]
    for c in (0,1):assert sum(v['cycles'] for v in r['cost_ledger'][c].values())==r['charged_cycles'][c] and r['charged_cycles'][c]+r['stall_cycles'][c]==r['accounted_until_cycles'][c]
    assert r['cost_ledger'][0]['PHY_TIMER']['cycles']==r['cost_ledger'][0]['PHY_TIMER']['events']*fee
    if fee==0:
     for key in ('cycles','banks','max_rf_poll_gap','peak_arena_bytes','checked_bytes','min_observed_job_deadline_margin'):assert r[key]==reference[key],key
    rows.append(r);print(fee,phase,r['banks'],r['scenario_pass'],flush=True)
 result=dict(scope=__doc__,rows=rows,service_budget_measured=False,all_SoC_costs_finalized=False,
  assumptions=['No initial pending timer callbacks; periodic releases on core0, fixed service budget including timer dispatch/scheduling/PHY wrapper/body.', 'Core0 can service timer before continuing owner work; receiver task priority policy remains to be fixed.', 'SPI IRQ/tick remain additive. Does not model the PHY changing RF data or extending hardware busy state.', 'Sampled phases and finite trace are not all-phase or WCET proofs. Zero-service case must reproduce the previous trace exactly.'],
  source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'experiments/s3_queue_audited_runtime.py',ROOT/'experiments/s3_joint_runtime.c',ROOT/'experiments/s3_joint_runtime.py',ROOT/'experiments/s3_queue_owner_runtime.py',OUT/'runtime.json']})
 (OUT/'periodic-runtime.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()

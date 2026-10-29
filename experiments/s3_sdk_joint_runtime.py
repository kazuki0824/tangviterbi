"""Same joint scheduler, with call-closed SDK instruction scenarios."""
import json,math,hashlib
from experiments.s3_joint_runtime import ROOT,run

def main():
 ledger=json.loads((ROOT/'reports/s3-sdk-cost-ledger/results.json').read_text())
 results=[]
 for rate,share,desc in [(16,8,9),(40,5,5),(40,6,5)]:
  root=ledger['roots'][str(desc)]
  def fee(key):return math.ceil(root[key]['inclusive_instructions']*11/10)
  costs=dict(SUBMIT_EMPTY=fee('submit_empty'),SUBMIT_DONE=fee('submit_done'),REAP_DONE=fee('reap_done'),WDT=math.ceil((root['feed_True']['inclusive_instructions']-root['feed_False']['inclusive_instructions'])*11/10),IRQ_START=fee('spi_irq_start'),IRQ_FIRST=fee('spi_irq_first'),IRQ_COMPLETE=fee('spi_irq_complete'))
  # REAP_RUNNING's existing 42/44 includes wrapper and is retained: SDK result
  # queue is not called while the hardware running flag is set.
  cases=[(rate,share,sl,100,1,st,20000,prep,1024) for sl in (256,512) for st in (0,10) for prep in (1024,2048,3072)]
  cases += [(rate,share,512,4000,1,0,20000,prep,1024) for prep in (1024,2048,3072)]
  r=run(cases,costs);r['descriptor_count']=desc
  r['dynamic_costs']['SPI_IRQ']='IRQ_FIRST once per port, then IRQ_START per launch; IRQ_COMPLETE per completion. Values are in fixed_cost_cycles; row irq_cycles=1 is an unused legacy argument.'
  results.append(r)
 out=dict(scope=__doc__,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'experiments/s3_sdk_joint_runtime.py',ROOT/'reports/s3-sdk-cost-ledger/results.json']},profiles=results,hardware_proven=False,remaining_allocations=['OWNER_SHELL','WORKER_SHELL','PACK_EMPTY','RF_BASE','RF_PREPARE','RF_SWITCH','RF_ACCEPT','COLLECT','TICK_IRQ'],excluded_waits=ledger['unresolved'],launch_timing='wire begins after entire launch handler charge; conservative relative to actual start near handler tail')
 target=ROOT/'reports/s3-sdk-cost-ledger/runtime.json';target.write_text(json.dumps(out,indent=2)+'\n')
 for profile in results:
  for r in profile['rows']:print({k:r[k] for k in ['rate','share','slice_pairs','prepare_per_iteration','stall_percent','requested_banks','banks','scenario_pass','native_fault','pack_fault','accept_reject_reason','attempted_arena_bytes','peak_arena_bytes']})
if __name__=='__main__':main()

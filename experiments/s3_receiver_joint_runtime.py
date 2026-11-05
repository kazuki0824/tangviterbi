"""Source-bounded main-loop costs connected to the existing real-C scheduler."""
import hashlib,json,math
from experiments.s3_joint_runtime import ROOT,run

def main():
 p=ROOT/'reports/s3-receiver-cost-ledger';ins=json.loads((p/'instructions.json').read_text())['paths'];sdk=json.loads((ROOT/'reports/s3-sdk-cost-ledger/results.json').read_text())['roots']
 ticks=json.loads((p/'tick.json').read_text())['paths'];irq_record=json.loads((p/'irq-entry.json').read_text());irq=irq_record['instructions_excluding_handler_and_window_traps'];switch_irq=irq_record['switch_instructions_excluding_handler_and_window_traps']
 n=lambda k:ins[k]['instructions']
 cycle=lambda instructions:(instructions*11+9)//10
 base=n('native_quiet')
 costs=dict(OWNER_SHELL=cycle(n('owner_shell_with_inline_poll')-28),WORKER_SHELL=cycle(n('worker_shell')),
 PACK_EMPTY=cycle(n('pack_raw_wrapper')+n('pack_empty_quantized')),PACK_SLICE=cycle(223+2*n('clock')+n('pack_raw_wrapper')),
 RF_BASE=cycle(base+14),RF_PREPARE=cycle(n('native_prepare')-base),RF_SWITCH=cycle(n('native_switch')-base),RF_ACCEPT=cycle(n('native_settling')-base),FILL_OVERHEAD=ins['fill_formula']['nonbody_per_span'],TICK0=cycle(ticks['handler_switch_0']['instructions']+switch_irq)+cycle(ticks['kernel_1']['instructions']+ticks['scheduler_same_task']['instructions']),TICK1=cycle(ticks['handler_switch_1']['instructions']+switch_irq)+cycle(ticks['kernel_0']['instructions']+ticks['scheduler_same_task']['instructions']),
 **{'COLLECT_'+str(k):cycle(n('collect_'+str(k))) for k in range(4)})
 profiles=[]
 for rate,share,desc in [(16,8,9),(40,5,5),(40,6,5)]:
  roots=sdk[str(desc)];fee=lambda k:cycle(roots[k]['inclusive_instructions'])
  c=dict(costs,SUBMIT_EMPTY=fee('submit_empty'),SUBMIT_DONE=fee('submit_done'),REAP_DONE=fee('reap_done'),WDT=cycle(n('feed_due')-n('feed_normal'))+fee('wdt_feed_0'),IRQ_START=cycle(roots['spi_irq_start']['inclusive_instructions']+irq),IRQ_FIRST=cycle(roots['spi_irq_first']['inclusive_instructions']+irq),IRQ_COMPLETE=cycle(roots['spi_irq_complete']['inclusive_instructions']+irq))
  cases=[(rate,share,sl,100,1,stall,20000,prep,1024) for sl in (256,512) for stall in (0,10) for prep in (1024,2048,3072)]
  cases += [(rate,share,512,4000,1,0,20000,prep,1024) for prep in (1024,2048,3072)]
  result=run(cases,c)
  result['dynamic_costs'].update(FILL='ceil((5 + sum_spans(41 + 17*floor(span/8) + 3*(span%8)))*1.1)',COLLECT='COLLECT_[owned_count]',TICK_IRQ='TICK0/TICK1 per 100Hz core interrupt; one tick/IRQ; same-task reselection, plus at most one peer kernel increment and one peer scheduler section of lock wait',SPI_IRQ='IRQ_FIRST per initial port launch, IRQ_START per subsequent launch, IRQ_COMPLETE per wire completion')
  result['lock_wait_model']={'tick_core0_extra_cycles':cycle(ticks['kernel_1']['instructions']+ticks['scheduler_same_task']['instructions']),'tick_core1_extra_cycles':cycle(ticks['kernel_0']['instructions']+ticks['scheduler_same_task']['instructions']),'wdt_extra_cycles':fee('wdt_feed_0'),'conditions':'Frozen two-task receiver. Only peer tick/scheduler uses kernel lock and only peer reset uses WDT lock during receiving; no higher-level IRQ extension. Competitor full function costs bound their own critical sections in the same instruction model. Each peer can arrive at most once in the modeled wait (10ms/2.5s periods).'}
  profiles.append(result)
 result=dict(profiles=profiles,hardware_wcet=False,all_application_costs_finalized=False,source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__).resolve(),p/'instructions.json',p/'tick.json',p/'irq-entry.json',ROOT/'reports/s3-sdk-cost-ledger/results.json']})
 (p/'runtime.json').write_text(json.dumps(result,indent=2)+'\n')
 for pr in profiles:
  for r in pr['rows']:print({k:r[k] for k in ['rate','share','slice_pairs','prepare_per_iteration','stall_percent','requested_banks','banks','scenario_pass','native_fault','pack_fault','accept_reject_reason','attempted_arena_bytes']})
from pathlib import Path
if __name__=='__main__':main()

"""One accounting boundary and transfer configuration; incomplete evidence is explicit."""
import hashlib,json
from pathlib import Path
from experiments.s3_arena_limits import capacity
from experiments.s3_native_spi_windows import wire_floor
from experiments.s3_reclaim_limits import reclaim_limits
from experiments.s3_settling_limits import limits
ROOT=Path(__file__).resolve().parents[1]

def report():
 # Inclusive components are disjoint by contract. No residual U is treated as
 # covering a component unless that coverage is separately quantified.
 components=[
 ('owner_shell','core0','N0','task-loop instructions, poll_rf wrappers, direct collect clock and feed checks; excludes all charged callees and WDT reset','declared quiet examples only'),
 ('worker_shell','core1','N1','task-loop instructions and feed checks; excludes packing and WDT reset','not fully counted'),
 ('packing','both','N0 on core0; N1 on core1','whole pack_slice, packing body and its clock callbacks; EMPTY and successful paths distinguished','body CFG coefficients available; wrapper/empty/state mixture incomplete'),
 ('rf_poll','core0','Nquiet+Nwait+Nswitch+Naccept+Nprepare=7*N0','native_poll body with clocks/MMIO/sink callbacks; excludes fill body','quiet path only; other paths and mixture incomplete'),
 ('fill','core0','7168 words per completed next-bank preparation; partial boundary counted separately','fill body with bank callback; excludes caller management and startup fill','per-bank instruction envelope15567 available; no cycle bound'),
 ('collect','core0','N0','s3_pp_collect body and all publication/release work','two examples counted; other states/concurrent transitions incomplete'),
 ('spi_submit','core0','attempts <=2*N0; successful transfers Q0+Q1','s3_pp_spi_submit, take, prepare, queue API; ISR excluded','20us is a scenario only; empty, success and lock paths incomplete'),
 ('spi_reap','core0','attempts <=2*N0; successful reaps D0+D1','s3_pp_spi_reap, driver result retrieval, complete; ISR excluded','running path38/40 instructions; other path coverage incomplete'),
 ('spi_irq','configured core','per host interval: <=6+2*floor(R/L) including carry-in','ISR entry/exit and handler CPU; excludes other interrupts','conditional arrival certificate; finite execution cost/refinement missing'),
 ('wdt_reset','each core','<=1+floor(R/600000000) in 240MHz cycles, if configured timeout5000ms','actual esp_task_wdt_reset call only; caller checks in shell','bounded frequency from source; execution/lock cost missing'),
 ('other_irq','configured core','tick100Hz from pinned config; other IRQ/IPC envelopes required','non-SPI interrupts; not counted again in CPU-active API or shell','cost and other event arrival bounds missing'),
 ('stall_and_block','affected core','per charged operation/lock; correlated DMA contention must be covered','memory/MMIO/window/lock elapsed additions not already included above','bounds missing; cannot set to zero'),
 ('startup_shutdown_fault','both','once per lifecycle, plus fault occurrence','RF-off init/calibration, teardown and fault paths; excluded from uninterrupted reception demand','functional lifecycle tested; elapsed costs not fully counted')]
 rows=[]
 for standard,rate,chunk in [('T',16,32768),('S',40,16384)]:
  samples=rate*1e6;wire=wire_floor(chunk)
  rows.append(dict(standard=standard,rate_samples_s=samples,transfer_bytes=chunk,
    physical_arena_bytes=131072,nominal_bank_rate_s=samples/12288,
    steady_successful_transfer_rate_s=samples*2.5/chunk,
    # The initial bank may have 11264 samples; this is a steady-stream interval only.
    steady_bank_rate_interval_s=[samples/14352,samples/12288],
    wire=wire,RF=limits(rate),reclaim=reclaim_limits(rate),
    capacity_at_four_max_banks=capacity(4*14352,0,transfer_bytes=chunk),
    accounting_complete=False,joint_schedule_evaluated=False))
 return dict(scope=__doc__,components=[dict(id=i,core=c,event_count=n,inclusive_scope=s,evidence=e) for i,c,n,s,e in components],
   total_cpu_demand='sum(exclusive component CPU costs * event counts); no inherited U0/U1 bucket',
   timing_rule='Same component elapsed costs plus once-counted interference must drive worker/owner/port events; average demand is not an elapsed upper bound.',
   rows=rows,remaining_for_step1=['Full state-dependent costs and owner/worker state frequencies, including failed polls.',
       'Define finite contention/IRQ budgets or sensitivity ranges with sourcing; no uncounted residual silently set to zero.'],
   remaining_for_step2=['A nonuniform schedule connected to the same complete cost inputs and actual ordering.',
       'Joint RF switch/preparation/reclaim, ordered DMA retirement and 128KiB obligations; existing periodic-scan results are not substituted.'],
   step1_complete=False,step2_complete=False,receiver_adopted=False,
   source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
     ['experiments/s3_joint_accounting.py','experiments/s3_raw_tasks.c','experiments/s3_native_capture.c',
      'experiments/s3_parallel_pack.c','experiments/s3_parallel_spi.c','experiments/s3_spi_transport.c',
      'experiments/s3_arena_limits.py','experiments/s3_native_spi_windows.py','experiments/s3_spi_prefix_response.py','experiments/s3_spi_irq_envelope.py']})
if __name__=='__main__':
 out=ROOT/'reports/s3-joint-accounting/results.json';r=report();out.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps([{k:x[k] for k in ('standard','transfer_bytes','steady_successful_transfer_rate_s','nominal_bank_rate_s')} for x in r['rows']],indent=2))

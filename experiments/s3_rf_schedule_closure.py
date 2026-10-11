"""RF polling blackout and per-core demand gates, under explicit design budgets.

This is not an RTOS implementation or measured WCET. It closes two holes in
the optimistic bank model: blocking both cores across a capture threshold and
charging SPI API CPU time as well as wire occupation. Failure excludes the
specified policy/budgets, never all possible kernels or schedules.
"""
import argparse
import json
import math
from pathlib import Path
from s3_bank_schedule import simulate
from s3_sct_schedule import PERIOD,PAGE,service

def capture_blackouts(phase_us=0,fft_us=500,tiles=1,poll_us=0,banks=1024):
 """No asynchronous preemption; threshold can be polled only outside tiles.

 Native poll switches at 12288 samples and rejects >2000 additional samples.
 Switch overshoot changes the next bank's threshold, so advance from actual
 switch time, rather than assuming a fixed-phase bank grid after a delay.
 """
 if not 0<=phase_us<PERIOD or fft_us<0 or tiles<1 or poll_us<0:
  raise ValueError('invalid blackout profile')
 tile_us=fft_us/tiles
 frame_us=fft_us+(tiles-1)*poll_us
 if frame_us>=PERIOD:raise ValueError('overlapping FFT periods')
 threshold=768.;peak=0.;late_limit_us=125.
 for bank in range(banks):
  at=threshold
  frame=math.floor((at-phase_us)/PERIOD)
  if frame>=0:
   offset=at-(phase_us+frame*PERIOD)
   tile=math.floor(offset/(tile_us+poll_us)) if tile_us+poll_us else tiles
   if tile<tiles and offset<tile*(tile_us+poll_us)+tile_us-1e-9:
    at=phase_us+frame*PERIOD+tile*(tile_us+poll_us)+tile_us
  delay=at-threshold;peak=max(peak,delay)
  if delay>late_limit_us+1e-9:
   return dict(conditional_pass=False,first_failed_bank=bank,
    worst_switch_lateness_us=peak,late_limit_us=late_limit_us,banks_completed=bank,
    phase_us=phase_us,tiles=tiles,fft_compute_us=fft_us,
    FFT_elapsed_with_poll_gaps_us=frame_us,poll_gap_us=poll_us)
  threshold=at+768.
 return dict(conditional_pass=True,first_failed_bank=None,worst_switch_lateness_us=peak,
  late_limit_us=late_limit_us,banks_completed=banks,phase_us=phase_us,tiles=tiles,
  fft_compute_us=fft_us,FFT_elapsed_with_poll_gaps_us=frame_us,poll_gap_us=poll_us)

def core_demand(mode='S',pack_cycles=4,fft_us=500,prepare_core=0,api_core=0,
                control_core=1,rs_cycles=0):
 """Steady-state necessary CPU demand for the concrete Octal/Quad route.

 RF stripe uses the minimum API invocation rate at these service capacities.
 API 20us is a CPU-active design scenario, not a promised driver bound; if
 part of it is waiting, substitute the measured active time and re-evaluate.
 Additional RPC API, CRC, IRQ, DMA/cache stalls and DSP are omitted (positive).
 """
 if mode not in ('T','S') or any(c not in (0,1) for c in (prepare_core,api_core,control_core)):
  raise ValueError('invalid owner')
 raw=16e6 if mode=='T' else 40e6
 rate=28.86e6*2/(203*8)
 cores=[raw*pack_cycles/240e6,0.]
 components=[dict(task='single packing owner',core=0,utilization=cores[0])]
 def add(task,core,u):cores[core]+=u;components.append(dict(task=task,core=core,utilization=u))
 add('native bank preparation budget',prepare_core,raw/12288*20000/240e6)
 add('control and poll budget',control_core,(10e6+8*raw/256)/240e6)
 if mode=='T':
  add('two-core FFT',0,fft_us/PERIOD);add('two-core FFT',1,fft_us/PERIOD)
  # 8 Quad input APIs, one Octal FFT-output API, and RF 3-page APIs.
  apis=9e6/PERIOD+40e6/(3*PAGE)
 else:
  octal_MBps=3*PAGE/service(3)
  octal_RF_MBps=min(100,octal_MBps)
  # Optimal API count: saturate the more API-efficient Octal first.
  apis=octal_RF_MBps*1e6/(3*PAGE)+(100-octal_RF_MBps)*1e6/PAGE
 add('SPI API active CPU scenario',api_core,apis*20e-6)
 if rs_cycles:add('RS compute only, no RPC/CRC',1,rate*rs_cycles/240e6)
 return dict(mode=mode,packing_cycles_per_sample=pack_cycles,FFT_elapsed_us=fft_us,
  prepare_core=prepare_core,api_core=api_core,control_core=control_core,
  RS_cycles_per_codeword_assumed=rs_cycles,components=components,core_utilization=cores,
  selected_budget_pass=all(x<1 for x in cores),
  total_utilization=sum(cores)/2,receiver_adopted=False,CPU_WCET_verified=False)

def report():
 blackouts=[capture_blackouts(p*PERIOD/256,tiles=tiles,poll_us=poll)
  for tiles,poll in ((1,0),(4,1),(5,1),(14,1)) for p in range(256)]
 demand=[core_demand(mode,c,fft,prep,api,ctrl,rs)
  for mode in ('T','S') for c in (4,6,8)
  for fft in ((500,513) if mode=='T' else (0,))
  for prep in (0,1) for api in (0,1) for ctrl in (0,1)
  for rs in ((0,) if mode=='T' else (0,2000,2500,3000))]
 bank_sensitivity=[simulate('T',c,fft_us=fft,phase_us=p*PERIOD/4,ring_bytes=65536)
  for c in (4,6) for fft in (500,513) for p in range(4)]
 return dict(scope=__doc__,blackouts=blackouts,per_core_demand=demand,
  bank_event_sensitivity=bank_sensitivity,
  summary=dict(blackout_passes={str(tiles):sum(r['conditional_pass'] for r in blackouts if r['tiles']==tiles)
   for tiles in (1,4,5,14)},blackout_phases_per_profile=256,
   demand_profiles=len(demand),selected_budget_passes=sum(r['selected_budget_pass'] for r in demand)),
  remaining=['joint preemptive schedule and RF actual poll jitter','RTOS/IRQ/CRC/RPC CPU costs',
   'target packing/FFT/RS WCET and tile durations','bank preparation and SPI active time bounds',
   'DMA and memory contention'],complete_estimate=False,receiver_adopted=False)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report(),indent=2)+'\n')

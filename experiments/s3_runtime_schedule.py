"""All-mode necessary timing bounds for the actual runtime32 ownership.

These are design scenarios, NOT measured WCET, not joint-event certification.
Bank preparation, every SPI API and packing stay on core0 as implemented.
Both FFT workers contribute separate core costs; full-frame DMA is retained.
A fail rejects this fixed route and specified costs only. Other routes and
implementations remain in the finite catalogue. No samples or bins are removed.
"""
import argparse
import json
from pathlib import Path
from s3_sct_schedule import service,PAGE


def terrestrial(points,gi,fft_us,pack_cycles=4,api_active_us=20,wire_api_us=20,
                prepare_cycles=20000,reorder_cycles=0):
 if points not in (2048,4096,8192) or gi not in (1/4,1/8,1/16,1/32):raise ValueError('ISDB-T mode/GI')
 if min(fft_us,pack_cycles,api_active_us,wire_api_us,prepare_cycles,reorder_cycles)<0:raise ValueError('negative budget')
 period=1008*points/8192*(1+gi);pages=4*points//PAGE
 raw_calls=40e6/(2*PAGE)  # T caps RF at two slots, leaving two for FFT return
 input_calls=pages*1e6/period;output_calls=1e6/period
 octal_RF=40*service(2,batch_us=wire_api_us)/(2*PAGE)
 octal_FFT=service(pages,batch_us=wire_api_us)/period
 quad_input=pages*service(1,lanes=4,batch_us=wire_api_us,segment_us=0)/period
 core0={'pack':16e6*pack_cycles/240e6,'FFT':fft_us/period,
        'prepare':16e6/12288*prepare_cycles/240e6,
        'API':(raw_calls+input_calls+output_calls)*api_active_us/1e6,
        'reorder':reorder_cycles/240/period}
 core1={'FFT':fft_us/period}
 best_frame=pages*service(1,lanes=4,batch_us=wire_api_us,segment_us=0)+fft_us+reorder_cycles/240+service(pages,batch_us=wire_api_us)
 return dict(points=points,GI=gi,period_us=period,slot_deadline_us=2*period,
  FFT_each_direction_MBps=4*points/period,
  assumed=dict(FFT_us=fft_us,pack_cycles=pack_cycles,API_active_us=api_active_us,
   API_wire_overhead_us=wire_api_us,bank_prepare_cycles=prepare_cycles,reorder_cycles=reorder_cycles),
  core0_components=core0,core1_components=core1,core_utilization=[sum(core0.values()),sum(core1.values())],
  core_spare_percent=[100*(1-sum(core0.values())),100*(1-sum(core1.values()))],
  fixed_route_utilization=dict(Octal=octal_RF+octal_FFT,Quad=quad_input),
  fixed_route_spare_percent=dict(Octal=100*(1-octal_RF-octal_FFT),Quad=100*(1-quad_input)),
  optimistic_same_frame_release_us=best_frame,
  optimistic_same_frame_slack_us=2*period-best_frame,
  necessary_scenario_pass=max(sum(core0.values()),sum(core1.values()),octal_RF+octal_FFT,quad_input)<=1 and best_frame<=2*period,
  measured_WCET=False,joint_schedule_verified=False,receiver_adopted=False)


def report():
 cases=[terrestrial(n,gi,500*n*(n.bit_length()-1)/(8192*13),api_active_us=active,wire_api_us=wire)
        for n in (2048,4096,8192) for gi in (1/4,1/8,1/16,1/32)
        for active,wire in ((0,20),(2,20),(20,20))]
 return dict(scope=__doc__,cases=cases,
  runtime32=dict(RF_ring_bytes=32768,FPGA_RF_store_bytes=16384,
   RF_queued_not_consumed_limit={'T':2,'S':4},RF_gray_bits=3,IQ_publication_gray_bits=2,
   credit_from='consumer retire, not DMA completion',
   RF_bank_samples=12288,T_poll_lateness_limit_us=125,S_poll_lateness_limit_us=50,
   minimum_page_reservation_for_current_bank_bytes=32768,
   S_zero_consumer_service_time_us_upper=4*PAGE/100,
   T_zero_consumer_service_time_us_upper=2*PAGE/40,
   cap_times_are_empty_buffer_upper_bounds=True),
  missing=['target tile/reorder/API/packing/preparation/RS WCET',
   'actual IRQ/poll jitter, stage waits and DMA/memory contention',
   'burst RF bank publication and consumption with bounded FPGA stalls',
   'physical ready/status IO timing and whole RF-to-TS top'],
  whole_performance_completed=False,receiver_adopted=False)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report(),indent=2)+'\n')

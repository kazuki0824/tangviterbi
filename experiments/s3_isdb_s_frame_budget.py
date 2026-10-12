"""Recheck conventional ISDB-S frame overhead, RS work and burst queues.

ITU-R BO.1408-1 Annex1 Appendix1 Table3: 48 slots, 8 frames/superframe,
203 transmitted bytes/slot, 38976 main symbols, 39936 total symbols/frame.
The existing 28.86 MBd parameter is an input, not derived from rounded Table4.
This is an ideal decoded-codeword arrival model, not a receiver/deinterleaver.
"""
import argparse,json
from pathlib import Path
SOURCE='https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf'
def scenario(mhz,frames=1024,symbol_rate=28860000):
 if mhz<=0 or frames<1 or symbol_rate<=0:raise ValueError('positive clock/frame/rate required')
 service=2667/mhz;next_free=0.;max_delay=0.;max_waiting=0
 # Packet data span four (203 main + 4 burst) groups. Final data word
 # appears before the final four burst symbols. TMCC occupies 192 symbols.
 for f in range(frames):
  for slot in range(1,49):
   arrival=(f*39936+192+slot*828-4)*1e6/symbol_rate
   delay=max(0.,next_free-arrival);max_delay=max(max_delay,delay)
   max_waiting=max(max_waiting,int(delay//service)+(delay>0))
   next_free=max(next_free,arrival)+service
 return dict(core_MHz=mhz,RS204_service_us=service,main_only_max_wait_us=max_delay,
  main_only_max_waiting_codewords=int(max_waiting),frames_simulated=frames,
  steady_main_RS_capacity_pass=mhz*1e6/2667>=48*symbol_rate/39936,
  decoded_arrivals_are_ideal=True,deinterleaver_and_TMCC_scheduling_verified=False,receiver_adopted=False)
def report():
 sr=28860000;mean=48*sr/39936;peak=sr/(4*203);burst=sr/828;tmcc=sr/(39936*8)
 return dict(scope=__doc__,source=SOURCE,symbol_rate_Hz_assumed=sr,
  frame_symbols=39936,main_symbols=38976,frame_period_us=39936e6/sr,
  superframe_period_us=8*39936e6/sr,main_fraction=38976/39936,
  main_RS_codewords_s=mean,TS_payload_Mbps=mean*188*8/1e6,
  instantaneous_no_overhead_RS_codewords_s=peak,
  main_with_burst_gap_RS_codewords_s=burst,TMCC_RS64_codewords_s=tmcc,
  current_RS204_clocks_per_codeword=2667,
  minimum_clock_MHz=dict(main_mean=2667*mean/1e6,
   no_overhead_zero_queue=2667*peak/1e6,with_burst_zero_queue=2667*burst/1e6,
   mean_if_TMCC_64_is_zero_expanded_into_existing_204_decoder=2667*(mean+tmcc)/1e6),
  frame_interleaver_payload_bytes=8*48*203,
  scenarios=[scenario(m) for m in (88.4251,90,92.6,93.15,94.7902,99)],
  implemented_modulation_scope='current S metric/trellis partial top: TC8PSK only',
  additional_required_for_general_S=['BPSK/QPSK K7 64-state path and puncture context',
   'TMCC RS64/48, frame/slot/TS identification',
   'main inter-frame deinterleaving and 47h sync restoration',
   'energy dispersal removal and complete receiver coupling'],
  historical_94_7902_MHz_is_not_a_universal_buffered_receiver_minimum=True,
  full_receiver_performance_verified=False,receiver_adopted=False)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report(),indent=2)+'\n')

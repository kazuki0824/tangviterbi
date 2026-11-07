"""Same-clock FIFO/scheduler arrival experiments, NOT a receiver arrival proof."""
from collections import deque
from fractions import Fraction as F
import json

CLOCK=F(1080,7)*1000000
T=F(26208)*1000000/F('1039.5')
S=F('50.505')*1000000

def simulate(segments, weighted, symbols=8):
 period=160380 # 1039.5 us at 1080/7 MHz, exactly
 rate=S/CLOCK
 upstream=[deque() for _ in range(4)];fifo=[deque() for _ in range(4)]
 rr=idle=ingress=service=share=0;acc=0;max_up=[0]*4;max_fifo=[0]*4;max_delay=[0]*4
 max_total=0;delivered=[0]*4;offered=[0]*4
 for clock in range(period*symbols):
  if clock%period==0:
   for c,n in enumerate(segments):
    upstream[c].extend([clock]*(2016*n));offered[c]+=2016*n
  acc+=rate.numerator
  if acc>=rate.denominator:
   acc-=rate.denominator;upstream[3].append(clock);offered[3]+=1
  # RTL sees pre-edge nonempty/full; do not introduce same-cycle bypass.
  put=None
  for off in range(4):
   c=(ingress+off)%4
   if upstream[c] and len(fifo[c])<16:put=c;break
  take=None
  if clock>=8 and clock%2==0:
   if service==127:
    idle=(idle+1)%4
   else:
    if weighted:
     for off in range(3):
      c=(rr+off)%3
      if fifo[c]:take=c;break
     if fifo[3] and (share!=2 or take is None):take=3
     if take is not None:
      share=(share+1)%3
      if take!=3:rr=(take+1)%3
    else:
     for off in range(4):
      c=(rr+off)%4
      if fifo[c]:take=c;rr=(c+1)%4;break
    if take is None:idle=(idle+1)%4
   service=(service+1)%128
  if take is not None:
   c=take;stamp=fifo[c].popleft();delivered[c]+=1;max_delay[c]=max(max_delay[c],clock-stamp+3)
  if put is not None:
   c=put;fifo[c].append(upstream[c].popleft());ingress=(c+1)%4
  for c in range(4):
   max_up[c]=max(max_up[c],len(upstream[c]));max_fifo[c]=max(max_fifo[c],len(fifo[c]))
  max_total=max(max_total,sum(map(len,upstream))+sum(map(len,fifo)))
 return dict(weighted=weighted,T_segments=segments,symbols=symbols,offered=offered,delivered=delivered,
  peak_upstream_words=max_up,peak_local_FIFO_words=max_fifo,peak_total_waiting_words=max_total,
  max_observed_arrival_to_ACS_complete_us=[float(F(x)*1000000/CLOCK) for x in max_delay],
  ending_waiting_words=[len(upstream[c])+len(fifo[c]) for c in range(4)],
  assumptions='Instant T symbol release; S perfectly paced; ideal work-conserving single-word ingress from unlimited upstream store; no SDRAM/CDC/other-stage stalls. Only these traces, not a bound for real reception.')

def run():
 capacity=CLOCK*F(127,256)
 return dict(core_MHz=float(CLOCK/1000000),local_FIFO=dict(contexts=4,words_each=16,bits_per_word=18,total_bits=1152),
  reserved_maintenance_percent=float(F(100,128)),
  useful_capacity_Mstep_s=float(capacity/1000000),demand_Mstep_s=float((T+S)/1000000),
  remaining_Mstep_s=float((capacity-T-S)/1000000),
  total_clock_margin_percent=float(100*(1-F(1,128)-2*(T+S)/CLOCK)),
  nonempty_queue_max_head_wait_clocks=dict(round_robin=10,weighted_conservative=22),
  per_context_max_idle_service_gap_clocks=1024,
  cold_initialization_preparation_clocks=8,
  grant_to_ACS_completion_clocks=3,
  whole_receiver_deadline_verified=False,
  traces=[simulate(s,w) for w in (False,True) for s in ([13,0,0],[1,5,7])])
if __name__=='__main__': print(json.dumps(run(),indent=2))

"""Necessary RS split budgets, not CPU WCET or an adopted receiver.

One hypothetical RPC page has a 16-byte header and 4080 record bytes.
An existing 80-bit SPI transaction header is additionally charged on the wire.
All codewords and all native RF samples are retained. CPU timing and the FPGA
RPC/Chien implementation have NOT been demonstrated by this scheduler.
"""
from itertools import product
import json,math
from s3_sct_schedule import service,PAGE
AVERAGE_RATE=6.52125e6/188
# BO.1408-1 section 5 permits omitting the sync byte (203 transmitted bytes,
# restored to 204 for RS). Charge continuous 2 payload bits/TC8PSK symbol,
# with no TMCC/burst gaps credited. This is stricter than TS-average rate.
RATE=28.86e6*2/(203*8)
BLOCKS=204
PERIOD=1e6*BLOCKS/RATE
CAP=(3*PAGE/service(3),PAGE/service(1,lanes=4,segment_us=0))
PROFILES={
 'CPU_all_RS': [('received_codewords',208,'FPGA_to_S3'),('TS_payload',192,'S3_to_FPGA')],
 'CPU_BM_Chien_Forney': [('syndromes',19,'FPGA_to_S3'),('corrections',20,'S3_to_FPGA')],
 'CPU_BM_Omega': [('syndromes',19,'FPGA_to_S3'),('lambda_omega',29,'S3_to_FPGA')],
 'CPU_BM_Omega_Forney': [('syndromes',19,'FPGA_to_S3'),('lambda',13,'S3_to_FPGA'),
                        ('roots',12,'FPGA_to_S3'),('magnitudes',12,'S3_to_FPGA')],
}

def rpc_time(pages,port):
 # Octal SCT can amortize a multi-page message; Quad charges one API/page.
 return service(pages) if port==0 else pages*service(1,lanes=4,segment_us=0)

def simulate(assignments,counts,batches=100,batch_us=20):
 """RF ring + periodic RPC messages, FIFO-order RF retirement, both SPI ports.

 RPC stages in a cycle belong to DIFFERENT batches; this models a pipelined
 solver with at least one batch of interstage slack, not zero-cost CPU work.
 RPC release times are a contract that the eventual CPU/Chien must satisfy.
 """
 jobs=[(b*PERIOD+j*PERIOD/len(counts),assignments[j],counts[j],j)
       for b in range(batches) for j in range(len(counts))]
 jobs.sort();next_job=0;t=0.;claimed=retired=0;done=set();ports=[None,None];waiting=[[],[]]
 peak=rpc_count=0;max_rpc_latency=0.;duration=batches*PERIOD
 while t<duration:
  for i,p in enumerate(ports):
   if p and p[0]<=t+1e-7:
    if p[1]=='RF':done.update(range(p[2],p[2]+p[3]))
    else:rpc_count+=1;max_rpc_latency=max(max_rpc_latency,t-p[2])
    ports[i]=None
  while retired in done:done.remove(retired);retired+=1
  while next_job<len(jobs) and jobs[next_job][0]<=t+1e-7:
   release,port,n,kind=jobs[next_job];waiting[port].append((release,n));next_job+=1
  available=math.floor(t*100/PAGE+1e-9)-claimed
  for i in (0,1):
   if ports[i]:continue
   if waiting[i]:
    release,n=waiting[i].pop(0)
    cost=(service(n,batch_us=batch_us) if i==0 else n*service(1,lanes=4,batch_us=batch_us,segment_us=0))
    ports[i]=(t+cost,'RPC',release,n);continue
   n=3 if i==0 else 1
   # Do not let one-page Quad transactions starve the three-page Octal batch.
   reserve=3 if i==1 and ports[0] is None and not waiting[0] else 0
   if available>=n+reserve:
    cost=service(n,batch_us=batch_us) if i==0 else service(1,lanes=4,batch_us=batch_us,segment_us=0)
    ports[i]=(t+cost,'RF',claimed,n);claimed+=n;available-=n
  times=[p[0] for p in ports if p]
  times.append((math.floor(t*100/PAGE+1e-9)+1)*PAGE/100)
  if next_job<len(jobs):times.append(jobs[next_job][0])
  nxt=min(times);assert nxt>t+1e-8
  peak=max(peak,math.ceil(nxt*100/PAGE-1e-9)-retired);t=nxt
 return dict(batches=batches,duration_us=duration,peak_RF_reserved_bytes=peak*PAGE,
    RF_ring_bytes=65536,maximum_RPC_completion_latency_us=max_rpc_latency,
    RPC_slot_deadline_us=PERIOD/len(counts),RPC_completed=rpc_count,
    conditional_contract_pass=peak*PAGE<=65536 and max_rpc_latency<=PERIOD/len(counts),
    CPU_release_contract_verified=False,physical_SPI_timing_verified=False)

def report():
 result=dict(codewords_per_second=RATE,batch_codewords=BLOCKS,batch_period_us=PERIOD,
  rate_basis='continuous 28.86 MSymbol/s, 2 inner-decoded bits/symbol, 203 transmitted bytes; no framing gaps credited',
  average_TS_reference_codewords_per_second=AVERAGE_RATE,
  source='https://www.itu.int/dms_pubrec/itu-r/rec/bo/R-REC-BO.1408-1-200204-I!!PDF-E.pdf#page=8',
  spare_core_cycles_per_codeword_at_240_MHz=240e6/RATE,CPU_budget_is_not_WCET=True,
  RF_MBps=100,existing_port_capacity_MBps=CAP,existing_aggregate_spare_MBps=sum(CAP)-100,
  RPC_header_bytes=16,wire_header_bits=80,receiver_adopted=False,profiles={})
 for name,records in PROFILES.items():
  counts=[math.ceil(BLOCKS/((PAGE-16)//size)) for _,size,_ in records]
  candidates=[]
  for assign in product((0,1),repeat=len(records)):
   occupied=[sum(rpc_time(n,p) for n,p in zip(counts,assign) if p==port)/PERIOD for port in (0,1)]
   available=sum(c*(1-u) for c,u in zip(CAP,occupied))
   row=dict(ports=['SPI2_Octal80' if p==0 else 'SPI3_Quad80' for p in assign],
    port_time_fraction=occupied,RF_remaining_capacity_MBps=available,RF_margin_MBps=available-100,
    necessary_bandwidth_pass=available>=100)
   if row['necessary_bandwidth_pass']:row['event_model']=simulate(assign,counts)
   candidates.append(row)
  result['profiles'][name]=dict(
    records=[dict(name=n,bytes=s,direction=d,pages=pg) for (n,s,d),pg in zip(records,counts)],
    RPC_padded_payload_MBps=sum(counts)*PAGE/PERIOD,
    unframed_minimum_MBps=sum(s for _,s,_ in records)*RATE/1e6,
    CPU_performance_pass=None,FPGA_fit_pass=None,communication_assignments=candidates,
    adopted=False,reason='CPU deadline and FPGA split implementation unverified; bandwidth screening alone cannot adopt')
 result['negative_control_40us_API']=simulate((1,1,1,1),(1,1,1,1),batches=20,batch_us=40)
 return result
if __name__=='__main__':print(json.dumps(report(),indent=2))

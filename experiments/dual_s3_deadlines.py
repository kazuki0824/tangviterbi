"""Conditional burst and tile schedules. Not hardware WCET or memory timing proof.

RS sources retain complete codewords in external memory until granted; no IQ
precision or sample-rate reduction. FFT bus service is a PARAMETER, not measured
SDRAM efficiency. Report negative as well as positive configurations.
"""
import argparse
from collections import deque
import json
import math
from pathlib import Path

CORE_MHZ = 162
RS_CYCLES = 2672  # decoder plus wrapper and minimum issue interval
S_PERIOD = 203 * 4 / 28.86
SUPERFRAME = 39936 * 8 / 28.86
T_PERIOD = 1039.5
T_WORDS = 4992 * 6 * (7/8) / (204*8)


def arrivals(frames=32, phase=0., paced=True, mode=3):
    horizon=frames*SUPERFRAME
    period=T_PERIOD / (2**(3-mode)); words=T_WORDS/(2**(3-mode))
    events=[]; previous=0
    for k in range(math.ceil(horizon/period)):
        count=math.floor((k+1)*words+1e-10)
        for seq in range(previous,count): events.append((k*period,0,seq))
        previous=count
    seq=0
    for f in range(frames):
        start=f*SUPERFRAME+phase
        for j in range(384):
            events.append((start+(j*S_PERIOD if paced else 0),1,seq));seq+=1
        events.append((start,2,f))
    return sorted(events)


def rs_schedule(events, mhz=CORE_MHZ, fifo_bytes=(4096,1024,128),
                service_cycles=RS_CYCLES, output_timing="end"):
    """Round-robin, whole-word output reservation; conservative lumped output.

    A payload arrives atomically within its slot. End/alternating/opposite
    timing probes include decoder-latency jitter; this finite set is not an
    adversarial proof. The consumers drain independently. Output credit can defer a
    grant. Queued inputs stay in SDRAM, not in the decoder's BSRAM allocation.
    """
    if mhz<=0 or service_cycles<=0: raise ValueError('positive service required')
    if output_timing not in ('end','alternating','opposite'):raise ValueError('unknown output timing')
    sizes=(188,188,48); rates=(27/8,81/8,1.)  # bytes/us, TMCC consumer assumption
    if any(c<s for c,s in zip(fifo_bytes,sizes)): raise ValueError('whole-word credit required')
    queues=[deque() for _ in range(3)]; level=[0.,0.,0.]; peak_out=[0.,0.,0.]
    peak_q=[0,0,0]; latency=[0.,0.,0.]; count=[0,0,0]; order=[-1,-1,-1]
    i=0;now=0.;last=0.;rr=0;peak_total=0;credit_wait=0.
    while i<len(events) or any(queues):
        for s in range(3):level[s]=max(0.,level[s]-(now-last)*rates[s])
        last=now
        while i<len(events) and events[i][0]<=now+1e-8:
            at,s,seq=events[i];queues[s].append((at,seq));i+=1
        for s in range(3):peak_q[s]=max(peak_q[s],len(queues[s]))
        peak_total=max(peak_total,sum(map(len,queues)))
        choices=[(rr+j)%3 for j in range(3)]
        eligible=[s for s in choices if queues[s] and level[s]+sizes[s]<=fifo_bytes[s]+1e-8]
        if not eligible:
            wake=[events[i][0]] if i<len(events) else []
            for s in choices:
                if queues[s]:wake.append(now+max(0.,level[s]+sizes[s]-fifo_bytes[s])/rates[s])
            nxt=min(wake)
            if any(queues):credit_wait+=nxt-now
            now=nxt;continue
        s=eligible[0]; at,seq=queues[s].popleft()
        if seq!=order[s]+1: raise AssertionError('source order violated')
        order[s]=seq;rr=(s+1)%3
        duration=service_cycles/mhz;now+=duration
        # Actual clean/8-error words finish at different offsets. Include
        # maximally separated start/end atomic emissions as jitter probes.
        fraction=1 if output_timing=='end' else (seq % 2 if output_timing=='alternating' else 1-seq%2)
        for j in range(3):level[j]=max(0.,level[j]-duration*fraction*rates[j])
        level[s]+=sizes[s];peak_out[s]=max(peak_out[s],level[s])
        if level[s]>fifo_bytes[s]+1e-6: raise AssertionError('reservation failed')
        for j in range(3):level[j]=max(0.,level[j]-duration*(1-fraction)*rates[j])
        last=now
        latency[s]=max(latency[s],now-at);count[s]+=1
    return dict(codewords=count,max_waiting_codewords=peak_q,max_total_waiting_codewords=peak_total,
                max_input_queue_bytes=peak_total*204,max_output_bytes=[math.ceil(x) for x in peak_out],
                max_latency_us=latency,output_credit_wait_us=credit_wait,finish_us=now,
                FIFO_bytes=list(fifo_bytes),service_cycles=service_cycles,core_MHz=mhz,output_timing=output_timing)


def fft_pass(tiles, read_us, compute_us, write_us, buffers=2):
    """Event simulation of a real two-buffer ownership constraint.

    Shared half-duplex bus, one compute unit, read -> compute -> write.
    Pending writes have bus priority. A buffer is reused only after its write.
    Compute consumes tiles in read order. No fictitious triple buffering.
    """
    if min(tiles,buffers)<=0 or min(read_us,compute_us,write_us)<=0:raise ValueError('positive work')
    states=['free']*buffers; ids=[-1]*buffers; read_next=0;done=0
    bus=None;cpu=None;now=0.;trace=[]
    while done<tiles:
        # Process completions before making new resource decisions.
        if bus and bus[0]<=now+1e-9:
            _,b,kind=bus;states[b]='ready' if kind=='read' else 'free'
            if kind=='write':done+=1
            bus=None
        if cpu and cpu[0]<=now+1e-9:
            _,b=cpu;states[b]='write_wait';cpu=None
        if cpu is None:
            ready=[b for b in range(buffers) if states[b]=='ready']
            if ready:
                b=min(ready,key=lambda x:ids[x]);states[b]='compute';cpu=(now+compute_us,b)
                trace.append(dict(tile=ids[b],buffer=b,op='compute',start_us=now,end_us=cpu[0]))
        if bus is None:
            writes=[b for b in range(buffers) if states[b]=='write_wait']
            free=[b for b in range(buffers) if states[b]=='free']
            if writes:
                b=min(writes,key=lambda x:ids[x]);kind='write';duration=write_us
            elif free and read_next<tiles:
                b=free[0];ids[b]=read_next;read_next+=1;kind='read';duration=read_us
            else:b=None
            if b is not None:
                states[b]=kind;bus=(now+duration,b,kind)
                trace.append(dict(tile=ids[b],buffer=b,op=kind,start_us=now,end_us=bus[0]))
        future=[x[0] for x in (bus,cpu) if x]
        if done<tiles:
            if not future:raise AssertionError('scheduler deadlock')
            now=min(future)
    return dict(duration_us=now,trace=trace)


def fft_schedule(n, efficiency=.55, bus_mhz=135, core_mhz=162, buffers=2):
    # Capture and final output run concurrently in external ping-pong frames.
    # Their bandwidth and all other clients are reserved before tile DMA.
    a,b={2048:(32,64),4096:(64,64),8192:(64,128)}[n]
    period=n/(512/63)*(33/32)
    background=2*n*4/period + 2*(4992*6/T_PERIOD) + 2*204/S_PERIOD + 10
    residual=bus_mhz*4*efficiency-background
    if residual<=0:return dict(n=n,pass_deadline=False,residual_MBps=residual)
    tile=8*b;count=n//tile
    transfer=4*tile/residual
    first=fft_pass(count,transfer,tile*(int(math.log2(b))+4)/core_mhz,transfer,buffers)
    second=fft_pass(count,transfer,tile*int(math.log2(a)) /core_mhz,transfer,buffers)
    total=first['duration_us']+second['duration_us']
    return dict(n=n,buffers=buffers,efficiency_assumed=efficiency,bus_MHz=bus_mhz,
                core_MHz=core_mhz,tile_complex_points=tile,tiles_per_pass=count,
                reserved_background_MBps=background,residual_MBps=residual,
                period_us=period,duration_us=total,slack_us=period-total,
                pass_deadline=total<=period,first=first,second=second,
                qualification='Conditional fluid bus service only; not a SDRAM controller timing proof')


def report():
    scenarios=[]
    for mode in (1,2,3):
        samples=[]
        for phase in range(16):
            for timing in ('end','alternating','opposite'):
                samples.append(rs_schedule(arrivals(16,phase*T_PERIOD/16,mode=mode),output_timing=timing))
        scenarios.append(dict(mode=mode,phase_points=16,superframes_per_phase=16,output_timing_patterns=3,
            max_total_waiting_codewords=max(x['max_total_waiting_codewords'] for x in samples),
            max_queue_per_source=[max(x['max_waiting_codewords'][s] for x in samples) for s in range(3)],
            max_latency_us=[max(x['max_latency_us'][s] for x in samples) for s in range(3)],
            max_output_bytes=[max(x['max_output_bytes'][s] for x in samples) for s in range(3)],
            max_credit_wait_us=max(x['output_credit_wait_us'] for x in samples)))
    return dict(shared_RS=dict(service_cycles=RS_CYCLES,service_us=RS_CYCLES/CORE_MHZ,
        modeled_paced_arrivals=scenarios,
        unpaced_S_superframe=rs_schedule(arrivals(16,paced=False)),
        small_output_FIFO=rs_schedule(arrivals(16),fifo_bytes=(188,188,48)),
        scope='Finite phase sweep, not an all-phase proof. External input staging, uninterrupted slot source, and output drain contracts required.'),
        FFT=[fft_schedule(n,e,buffers=b) for e in (.55,.65,.75) for b in (1,2) for n in (2048,4096,8192)],
        receiver_adopted=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report(),indent=2)+'\n')

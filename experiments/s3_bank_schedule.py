#!/usr/bin/env python3
"""Necessary-condition event model: burst-published RF banks, packing and DMA.

Unlike s3_sct_schedule this retains unconsumed samples in the three raw banks.
One serialized packing owner runs on core0; a T FFT blocks both cores. Quad IQ
arrival precedes FFT; slot reuse is two symbol periods after input starts.
SPI API time is charged to the wire service, NOT scheduled on the CPU here.
Therefore passes are optimistic, never a joint CPU/IRQ WCET certificate.
"""
import argparse
import json
import math
from pathlib import Path
from s3_sct_schedule import service, PERIOD, PAGE


def simulate(mode='T', pack_cycles=6, fft_us=500, bank_samples=12288,
             phase_us=0, duration_us=100000, batch_us=20, segment_us=.25, ring_bytes=32768):
    rate = 16 if mode == 'T' else 40
    bank_period = bank_samples/rate
    # Upstream prep reservation: 20000 CPU cycles plus 1024 sample pairs.
    # Actual sentinel/reset lead times still need to be measured.
    prep_lead = 20000/240 + 1024/rate
    t = 0.; next_bank = bank_period; bank_id=0
    banks=[]; packed=0.; claimed=retired=0; done=set(); ports=[None,None]
    producer=None; fft_due=phase_us; frames=[]; quad=None; fft_busy_until=0.
    peak_raw=peak_ring=0.; releases=[]; fault=None; packing_cpu_us=0.
    octal_fft=service(8,batch_us=batch_us,segment_us=segment_us)
    quad_input=8*service(1,lanes=4,batch_us=batch_us,segment_us=0)
    for events in range(2_000_000):
        # Complete before deadline checking; unlike a real implementation,
        # zero-cost event handling makes this an optimistic necessary test.
        if producer and producer[0]<=t+1e-8:
            _,n=producer; producer=None; banks[0]['left']-=n; packed+=n*2.5
            if not banks[0]['left']: banks.pop(0)
        for i,p in enumerate(ports):
            if p and p[0]<=t+1e-8:
                if p[1]=='RF': done.update(range(p[2],p[2]+p[3]))
                else:
                    f=p[2]; releases.append(t-f['arrival']);frames.remove(f)
                ports[i]=None
        while retired in done: done.remove(retired);retired+=1
        if quad and quad[0]<=t+1e-8:
            quad[1]['ready']=t; quad=None
        if mode=='T' and t>=fft_due-1e-8:
            frames.append({'arrival':fft_due,'deadline':fft_due+2*PERIOD,
                           'ready':None,'computed':None,'sent':False})
            fft_due+=PERIOD
        if t>=next_bank-1e-8:
            if any(b['id']==bank_id%3 for b in banks): fault='raw_bank_overwrite';break
            banks.append({'id':bank_id%3,'left':bank_samples,
                          'deadline':next_bank+2*bank_period-prep_lead})
            bank_id+=1;next_bank+=bank_period
        if any(b['deadline']<=t+1e-8 for b in banks): fault='raw_bank_prep_deadline';break
        if any(f['deadline']<t-1e-8 for f in frames): fault='FFT_slot_reuse';break
        if mode=='T':
            if quad is None:
                f=next((f for f in frames if f['ready'] is None),None)
                if f: quad=(t+quad_input,f)
            f=next((f for f in frames if f['ready'] is not None and f['computed'] is None),None)
            if f and producer is None and t>=fft_busy_until-1e-8:
                fft_busy_until=t+fft_us;f['computed']=fft_busy_until
        if ports[0] is None:
            f=next((f for f in frames if f['computed'] is not None and
                    f['computed']<=t+1e-8 and not f['sent']),None)
            if f:
                ports[0]=(t+octal_fft,'FFT',f,0);f['sent']=True
            else:
                available=math.floor((packed+1e-6)/PAGE)-claimed
                n=3 if available>=3 else 0
                # Do not start RF that would force a known FFT slot miss.
                ff=next((f for f in frames if f['computed'] is not None and not f['sent']),None)
                while n and ff and max(t+service(n,batch_us=batch_us,segment_us=segment_us),ff['computed'])+octal_fft>ff['deadline']+1e-8: n-=1
                if n:
                    ports[0]=(t+service(n,batch_us=batch_us,segment_us=segment_us),'RF',claimed,n);claimed+=n
        if mode=='S' and ports[1] is None:
            if math.floor((packed+1e-6)/PAGE)>claimed:
                ports[1]=(t+service(1,lanes=4,batch_us=batch_us,segment_us=0),'RF',claimed,1);claimed+=1
        if producer is None and banks and t>=fft_busy_until-1e-8:
            free=ring_bytes-(packed-retired*PAGE)
            n=min(256,banks[0]['left'],math.floor((free+1e-8)/2.5))
            if n:
                elapsed=n*pack_cycles/240
                producer=(t+elapsed,n);packing_cpu_us+=elapsed
        peak_raw=max(peak_raw,sum(b['left'] for b in banks)*4)
        peak_ring=max(peak_ring,packed-retired*PAGE+(producer[1]*2.5 if producer else 0))
        nxt=[next_bank,*[b['deadline'] for b in banks],*[p[0] for p in ports if p]]
        if producer:nxt.append(producer[0])
        if mode=='T':
            nxt.append(fft_due)
            if quad:nxt.append(quad[0])
            nxt.extend(f['computed'] for f in frames if f['computed'] is not None and f['computed']>t+1e-8)
        nxt=[x for x in nxt if x>t+1e-8]
        if not nxt:fault='event_deadlock';break
        t=min(nxt)
        if t>duration_us:break
    else:raise RuntimeError('event limit')
    return {'mode':mode,'pack_cycles_per_sample_assumed':pack_cycles,'FFT_assumed_us':fft_us,
            'phase_us':phase_us,'duration_us':duration_us,'simulated_until_us':min(t,duration_us),
            'API_batch_assumed_us':batch_us,'SCT_gap_assumed_us':segment_us,
            'ring_bytes':ring_bytes,'bank_samples':bank_samples,'bank_period_us':bank_period,'prep_lead_assumed_us':prep_lead,
            'maximum_pending_raw_bytes':peak_raw,'maximum_ring_reserved_bytes':peak_ring,
            'FFT_completed':len(releases),'maximum_slot_release_us':max(releases,default=None),
            'slot_deadline_us':2*PERIOD if mode=='T' else None,
            'packing_core_utilization_lower_bound':rate*pack_cycles/240,
            'packing_plus_FFT_core0_utilization_lower_bound':rate*pack_cycles/240+(fft_us/PERIOD if mode=='T' else 0),
            'failure':fault,'optimistic_event_pass':fault is None,
            'receiver_adopted':False,'CPU_IRQ_WCET_verified':False}


def report():
    return {'scope':__doc__,'runs':[simulate(mode,c,phase_us=p,duration_us=100000,ring_bytes=ring)
            for mode in ('T','S') for ring in (32768,49152,65536) for c in (4,6,8)
            for p in ((0,PERIOD/4,PERIOD/2,3*PERIOD/4) if mode=='T' else (0,))]}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report(),indent=2)+'\n')

"""Conditional T soft-buffer service experiment; not a whole receiver proof.

T symbols are already committed to SDRAM at release (write latency excluded).
A hypothetical arbiter delivers at most 32 B to one T cache every gap clocks.
S is perfectly paced directly into a bounded soft FIFO; S deinterleaver absent.
Byte ingress skips blocked depuncturers. All soft bytes preserved.
"""
from collections import deque
from fractions import Fraction
import json

CLOCK = Fraction(1080000000, 7)
MASKS = [('1','1'),('10','11'),('101','110'),('10101','11010'),('1000101','1111010')]


def simulate(mode=3, segments=(1,5,7), gap=160, symbols=4, rate=4, service_phase=None):
    assert gap > 0 and mode in (1,2,3) and len(segments)==3 and sum(segments)==13
    if service_phase is None: service_phase=gap-1
    assert 0<=service_phase<gap
    period=40095*(1<<(mode-1))
    sizes=[n*96*(1<<(mode-1))*6 for n in segments]
    banks=[None,None]; cache=[deque() for _ in range(4)]
    pairs=[deque() for _ in range(4)]; pending=[None]*4
    phase=[0]*4; have=[None]*4
    ingress=pair_rr=t_rr=share=service=mem_rr=0
    sacc=0; peak_cache=[0]*4; peak_mem=0; completed=[0]*symbols
    read_done=[None]*symbols; acs_done=[None]*symbols
    produced=[0]*4; consumed=[0]*4; offered=[0]*4; served=[0]*4
    overflow=None; deadline_misses=[]; max_s_fifo=256
    mx,my=MASKS[rate]; steps_per_symbol=sum(sizes)*len(mx)//sum(int(x) for x in mx+my)
    # S max QPSK 7/8: 57.72 MB/s. T can use any rate in model.
    for clk in range(period*(symbols+1)):
        if clk%period==0 and clk//period<symbols:
            symbol=clk//period; slot=symbol%2
            if banks[slot] is not None:
                overflow=dict(clock=clk,kind='T bank reused before read complete',symbol=symbol);break
            banks[slot]=[symbol,sizes.copy()]
            for c in range(3): offered[c]+=sizes[c]
        if clk<period*symbols:
            sacc+=404040000  # 57.72e6 / (1080e6/7), exact
            if sacc>=1080000000:
                sacc-=1080000000
                if len(cache[3])>=max_s_fifo:
                    overflow=dict(clock=clk,kind='S soft FIFO overflow');break
                cache[3].append(-1);offered[3]+=1
        # Hypothetical completed memory service. No promise of real grants.
        if clk%gap==service_phase:
            live=sorted((b for b in banks if b is not None),key=lambda b:b[0])
            if live:
                b=live[0]
                for off in range(3):
                    c=(mem_rr+off)%3
                    n=min(32,b[1][c])
                    if n and len(cache[c])+n<=64:
                        cache[c].extend([b[0]]*n);b[1][c]-=n;mem_rr=(c+1)%3
                        if not any(b[1]):
                            read_done[b[0]]=clk;banks[b[0]%2]=None
                        break
        # Combinational decisions use old registered counts (no bypass).
        put=next((c for off in range(4) if pending[c:=(pair_rr+off)%4] is not None and len(pairs[c])<16),None)
        byte=next((c for off in range(4) if cache[c:=(ingress+off)%4] and (pending[c] is None or put==c)),None)
        take=None
        if clk>=8 and clk%2==0:
            if service!=127:
                take=next((c for off in range(3) if pairs[c:=(t_rr+off)%3]),None)
                if pairs[3] and (share!=2 or take is None):take=3
            service=(service+1)%128
        if take is not None:
            stamp=pairs[take].popleft();served[take]+=1;share=(share+1)%3
            if take!=3:
                t_rr=(take+1)%3;completed[stamp]+=1
                if completed[stamp]==steps_per_symbol:
                    acs_done[stamp]=clk+3
                    if clk+3>=(stamp+2)*period: deadline_misses.append(stamp)
        if put is not None:
            pairs[put].append(pending[put]);pending[put]=None;pair_rr=(put+1)%4
        if byte is not None:
            c=byte;stamp=cache[c].popleft();consumed[c]+=1;ingress=(c+1)%4
            x,y=(MASKS[4] if c==3 else (mx,my));p=phase[c]
            if x[p]=='1' and y[p]=='1' and have[c] is None:have[c]=stamp
            else:
                if have[c] is not None: assert have[c]==stamp
                pending[c]=stamp;have[c]=None;phase[c]=(p+1)%len(x);produced[c]+=1
        for c in range(4): peak_cache[c]=max(peak_cache[c],len(cache[c]))
        peak_mem=max(peak_mem,sum(sum(b[1]) for b in banks if b is not None))
    remaining_soft=[len(cache[c])+int(have[c] is not None) for c in range(4)]
    # Conservation at byte input, independent of the queue scheduling policy.
    for c in range(3):
        unread=sum(b[1][c] for b in banks if b is not None)
        assert offered[c]==consumed[c]+len(cache[c])+unread
    assert offered[3]==consumed[3]+len(cache[3])
    assert all(produced[c]==served[c]+len(pairs[c])+int(pending[c] is not None) for c in range(4))
    return dict(mode=mode,segments=list(segments),gap_clocks=gap,symbols=symbols,rate=rate,service_phase=service_phase,
        sustained_read_rate_necessary_pass=32*period>=gap*sum(sizes),
        reserved_read_MBps=float(CLOCK*32/gap/1000000),symbol_period_clocks=period,
        T_two_bank_bytes=2*sum(sizes),T_cache_bytes=192,S_soft_FIFO_bytes=max_s_fifo,
        peak_unread_T_bytes=peak_mem,peak_soft_cache_bytes=peak_cache,
        overflow=overflow,deadline_misses=deadline_misses,
        read_complete_latency_clocks=[None if t is None else t-i*period for i,t in enumerate(read_done)],
        ACS_complete_latency_clocks=[None if t is None else t-i*period for i,t in enumerate(acs_done)],
        all_T_symbols_completed=all(t is not None for t in acs_done),
        offered_soft=offered,consumed_soft=consumed,produced_pairs=produced,served_pairs=served,
        remaining_soft_including_partial=remaining_soft,
        conditional_trace_pass=overflow is None and not deadline_misses and all(t is not None for t in acs_done))


def report():
    return dict(scope=__doc__,physical_memory_qualified=False,whole_receiver_verified=False,
        max_gap_necessary_clocks=float(Fraction(40095*32,7488)),
        required_T_read_MBps=float(Fraction(7488)*CLOCK/40095/1000000),
        traces=[simulate(m,s,g) for m in (1,2,3) for s in ((13,0,0),(1,5,7)) for g in (160,170,192)],
        long_traces=[simulate(1,s,g,symbols=16) for s in ((13,0,0),(1,5,7)) for g in (160,170,192)],
        phase_traces=[simulate(3,(1,5,7),160,service_phase=p) for p in range(0,160,20)])

if __name__=='__main__':print(json.dumps(report(),indent=2))

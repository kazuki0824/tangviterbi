"""Concrete masked dense-ring trace, preserving every 8-bit LLR.

This is a memory-client contract, NOT a frequency deinterleaver implementation.
T vectors arrive grouped by equal delay; grouping/reorder cost is outside it.
S uses a CW ring with sequential 204-byte words (not its bit/frame permutation).
Capture/output traffic uses a separate reserved staging region, not active FFT
buffers. Thus this test cannot establish RF-to-FFT ownership end to end.
"""
from dual_memory_contract import groups

S_PERIOD_NS=203*4/28.86*1000

def make_trace(mode, frames, phase_ns=0, isolate=False, layers=None, linear=False):
    r=1 << (mode-1); period=259875*r
    layers=layers or [(1,4//r),(1,8//r),(11,16//r)]
    gs=groups(mode,layers); base=262144; rings=[]
    for delay,size in gs.items():
        if delay:
            rings.append((base,delay,size));base+=((delay*size+31)//32)*32
    if base>6*1024**2:raise ValueError('T ring overlaps S region')
    events=[];seq=0
    def add(at,deadline,write,byte_addr,data=0,mask=0,source=0):
        nonlocal seq
        events.append((int(at),seq,int(deadline),write,byte_addr//4,data,mask,source));seq+=1
    horizon=frames*period
    # Group ordering is a producer contract; all requests for a vector arrive
    # together when its complete LLR payload is ready. No uniform-byte shortcut.
    for f in range(frames):
        offset=0
        for group,(start,delay,size) in enumerate(rings):
            offset+=size
            at=f*period+phase_ns+offset*period/(13*96*r*6)
            addr=start+((f+1531)%delay)*size
            for block in range(addr//32*32,addr+size,32):
                mask=(1<<32)-1;data=0
                for b in range(32):
                    if addr<=block+b<addr+size:
                        mask&=~(1<<b)
                        value=(f*73+group*19+block+b-addr)&255
                        data|=value<<(8*b)
                add(at,at+period,False,block,source=0)
                add(at,at+period,True,block,data,mask,source=0)
    # CW arrivals at the deliberately conservative no-overhead peak rate.
    k=0
    while k*S_PERIOD_NS<horizon:
        at=k*S_PERIOD_NS+phase_ns;start=5953024+(k%384)*224
        for j in range(7):
            size=min(32,204-j*32)
            mask=((1<<32)-1)^((1<<size)-1)
            data=sum(((k*7+j*32+b)&255)<<(8*b) for b in range(size))
            add(at,at+S_PERIOD_NS,True,start+j*32,data,mask,1)
        for j in range(7):add(at,at+S_PERIOD_NS,False,start+j*32,source=1)
        k+=1
    # Two additional Q15 frame transfers, with one complete BL8 arriving at
    # each sample-group boundary. Separately owned staging only.
    n=1 << (mode+10)
    for f in range(frames):
        for j in range(n//8):
            at=f*period+(j+1)*period/(n//8)+phase_ns
            addr=6125056+(j%1024)*32
            data=sum(((f*123+j*8+b)&0xffffffff)<<(32*b) for b in range(8))
            add(at,at+period,True,addr,data,source=2)
            add(at,at+period,False,addr,source=2)
    # Explicit 10 MB/s management reservation, not silently omitted.
    for k in range(int(horizon/3200)):
        at=k*3200+phase_ns
        add(at,at+period,k%2==0,6190592+(k//2%1024)*32,k,source=3)
    if isolate:
        mapped=[]
        for at,seq,deadline,write,address,data,mask,source in events:
            offset=address-65536
            page,col=divmod(offset,256)
            if linear:bank,row=divmod(page,2048)
            else:row,bank=divmod(page,3)
            physical=(row*4+bank+1)*256+col
            if not 0<=physical<2097152:raise ValueError('physical capacity')
            mapped.append((at,seq,deadline,write,physical,data,mask,source))
        events=mapped
    events.sort()
    memory={};initial=int.from_bytes(bytes.fromhex('dec0adde')*8,'little')
    result=[]
    for at,_,deadline,write,address,data,mask,source in events:
        old=memory.get(address,initial)
        if write:
            new=old
            for b in range(32):
                if not mask>>b&1:new=(new&~(255<<(b*8)))|(data&(255<<(b*8)))
            memory[address]=new
        result.append(dict(at=at,deadline=deadline,write=int(write),address=address,
                           data=data,mask=mask,expected=0 if write else old,source=source))
    return result,dict(mode=mode,layers=layers,T_ring_bytes=base-262144,
                       source_requests=[sum(x['source']==s for x in result) for s in range(4)],
                       duration_ns=horizon,phase_ns=phase_ns,bank_isolation=isolate,background_layout='linear' if linear else 'striped')

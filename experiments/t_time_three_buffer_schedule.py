"""Three rotating scratch buffers and in-place 16x16 transpose schedule.
This is a request producer model, not a whole receiver or synthesizable scheduler.
"""
from experiments.t_time_block_layout import allocation,spans
from experiments.t_time_interleaver_layout import LENGTHS


def roles(block):
    # Input block b, transform b-1, output b-2 are disjoint for the whole epoch.
    return block%3,(block-1)%3,(block-2)%3


def requests(mode=3, batch=100, serialized_bytes=False, competing=False):
    entries,ring,scratch=allocation(mode,[max(LENGTHS[mode])]*13)
    n=len(entries);period=40095*(1<<(mode-1));duration=16*period
    incoming,processing,outgoing=roles(batch)
    starts=[ring+i*scratch for i in range(3)]
    streams=[[]for _ in range(6)]
    # Descriptor: release clock, write, byte address, pre clocks, post clocks,
    # absolute completion deadline. Ordered per producer, no bypass.
    def add(client,wr,address,release=0,pre=0,post=0,deadline=duration):
        assert address%32==0 and 0<=address<8388608
        streams[client].append((release,int(wr),address,pre,post,deadline))
    for symbol in range(16):
        for offset in range(0,n*6,32):
            add(0,True,starts[incoming]+symbol*n*6+offset,symbol*period,deadline=(symbol+1)*period)
            add(1,False,starts[outgoing]+symbol*n*6+offset,symbol*period,deadline=(symbol+1)*period)
    for first in range(0,n,16):
        # Entire tile is captured before any source position is overwritten.
        for time in range(16):
            address=starts[processing]+time*n*6+first*6
            for offset in range(0,96,32):add(2,False,address+offset,post=32 if serialized_bytes else 0)
        for _,_,depth,base,size in entries[first:first+16]:
            if not depth:continue
            for address in spans(base,((batch-1)*16)%size*6,96,size*6):
                add(2,True,address,pre=32 if serialized_bytes else 0)
            start=(((batch-1)*16-depth)%size)*6
            bursts=spans(base,start,96,size*6)
            remaining=96+start%32
            for address in bursts:
                consumed=min(32,remaining);remaining-=consumed
                add(2,False,address,post=consumed if serialized_bytes else 0)
        for time in range(16):
            address=starts[processing]+time*n*6+first*6
            for offset in range(0,96,32):add(2,True,address+offset,pre=32 if serialized_bytes else 0)
    other=ring+3*scratch
    if competing:
        for symbol in range(16):
            for offset in range(0,n*6,32):
                add(3,True,other+(symbol%2)*n*6+offset,symbol*period,deadline=(symbol+1)*period)
                add(3,False,other+((symbol+1)%2)*n*6+offset,symbol*period,deadline=(symbol+1)*period)
            # S frame / management demand from the old contention fixture.
            # Synthetic locality, not a derived S interleaver address sequence.
            for j in range(268*(1<<(mode-1))):
                add(4,j%2==0,other+59904+(j%128)*32,symbol*period,deadline=(symbol+1)*period)
            # Existing outer FFT cache traffic proxy; only Mode3 used for this run.
            for j in range(2048):
                add(5,j%2==0,other+59904+77952+(j%512)*32,symbol*period+j*period//2048,deadline=(symbol+1)*period)
    assert other+59904+77952+16384<=8388608
    return streams,dict(mode=mode,batch=batch,period_clocks=period,epoch_clocks=duration,
                       ring_bytes=ring,scratch_bytes_each=scratch,three_scratch_end=other,
                       remaining_after_Tspill_Sframe_FFT=8388608-other-59904-77952-16384,
                       tile_bytes=16*16*6,roles=dict(incoming=incoming,processing=processing,outgoing=outgoing),
                       requests_per_client=list(map(len,streams)),
                       serial_transform_byte_clocks=sum(x[3]+x[4]for x in streams[2]),
                       serialized_bytes=serialized_bytes,competing=competing,
                       real_TTI_addresses=True,S_and_FFT_are_proxies=True,
                       cold_fill_and_whole_receiver_verified=False)

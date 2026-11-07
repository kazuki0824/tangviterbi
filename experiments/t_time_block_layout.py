"""16-symbol batching reference, exact delay and aligned BL8 addresses.
Six existing soft bytes/carrier are preserved. This is NOT integrated RTL.
Input/output scratch traffic is charged four times (write/read each).
"""
from experiments.t_time_interleaver_layout import layout,LENGTHS
import json
BLOCK=16

def spans(base,start,count,size):
    """Aligned 32-byte bursts touching a circular byte interval."""
    result=[]
    while count:
        n=min(count,size-start)
        result.extend(range((base+start)//32*32,(base+start+n+31)//32*32,32))
        count-=n;start=0
    return result

def allocation(mode,lengths):
    entries,_=layout(mode,lengths);result=[];base=0
    for segment,carrier,_,depth in entries:
        # Extra block ensures reads survive writing the entire newest block.
        size=((depth+BLOCK+BLOCK-1)//BLOCK)*BLOCK if depth else 0
        result.append((segment,carrier,depth,base,size))
        base+=size*6
    scratch=len(entries)*BLOCK*6
    return result,base,scratch

def traffic(mode,lengths,batch=100):
    entries,stored,scratch=allocation(mode,lengths)
    write=read=0
    for _,_,depth,base,size in entries:
        if not depth:continue
        write+=len(spans(base,(batch*BLOCK)%size*6,BLOCK*6,size*6))
        read+=len(spans(base,(batch*BLOCK-depth)%size*6,BLOCK*6,size*6))
    # Four complete sequential passes; tile padding/alignment excluded.
    scratch_requests=4*((scratch+31)//32)
    return dict(mode=mode,lengths=lengths,ring_bytes=stored,
                two_scratch_buffers_bytes=2*scratch,
                remaining_of_8MiB=8388608-stored-2*scratch,
                remaining_with_three_scratch=8388608-stored-3*scratch,
                remaining_with_four_scratch=8388608-stored-4*scratch,
                remaining_four_scratch_plus_Tspill_Sframe=8388608-stored-4*scratch-59904-77952,
                ring_write_BL8=write,ring_read_BL8=read,
                scratch_BL8=scratch_requests,
                BL8_per_symbol=(write+read+scratch_requests)/BLOCK,
                scope='Address/count model; arbitration, transpose RTL, buffer ownership and other-stage storage are unverified',
                adopted=False)

class DelayBlock:
    """One carrier, explicit ring; input values may represent all six bytes."""
    def __init__(self,depth):
        self.depth=depth
        self.size=((depth+31)//16)*16 if depth else 0
        self.ring=[None]*self.size
        self.time=0
    def push(self,values):
        if len(values)!=16:raise ValueError('exactly 16 samples')
        if not self.depth:self.time+=16;return list(values)
        for k,v in enumerate(values):self.ring[(self.time+k)%self.size]=v
        out=[None if self.time+k<self.depth else self.ring[(self.time+k-self.depth)%self.size] for k in range(16)]
        self.time+=16
        return out

if __name__=='__main__':
    print(json.dumps({'scope':__doc__,'cases':[traffic(m,[max(LENGTHS[m])]*13)for m in LENGTHS]},indent=2))

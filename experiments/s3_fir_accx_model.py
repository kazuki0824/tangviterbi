"""Small TRM semantic interpreter for this kernel's disassembly, NOT a CPU emulator.
No encoding, timing, ABI window spill, interrupt or cache simulation.
"""
import re
import struct

def instructions(text, symbol):
    body=text.split('<'+symbol+'>:',1)[1].split('\n\n',1)[0]
    result=[]
    for line in body.splitlines():
        m=re.match(r'\s*[0-9a-f]+:\s+[0-9a-f]+\s+(\S+)(?:\s+(.*))?$',line)
        if m:
            result.append((m[1],[a.strip() for a in (m[2] or '').split(',') if a.strip()]))
            # These audited kernels are straight-line and return exactly once.
            # Alignment NOPs following retw belong to no executed path.
            if m[1]=='retw.n': break
    return result

def execute(code, iv, qv, coeff, i_offset=0, q_offset=0):
    # Offsets are byte offsets within an aligned block; caller supplies readable
    # padding before/after the wanted history, independently for I and Q.
    regions={}; reads=[]
    for base,offset,values in [(0x1000,i_offset,iv),(0x2000,q_offset,qv),(0x3000,0,coeff)]:
        size=((offset+len(values)*2+15)//16)*16
        if base != 0x3000 and (offset+len(values)*2)%16==0: size+=16
        data=bytearray([0xA5]*size)
        data[offset:offset+len(values)*2]=struct.pack('<'+'h'*len(values),*values)
        regions[base]=data
    a={'a2':0x1000+i_offset,'a3':0x2000+q_offset,'a4':0x3000,'a5':0x4000}
    q={}; acc=0; sar=0; stores={}
    def load(addr):
        addr &= ~15
        for base,data in regions.items():
            if base<=addr and addr+16<=base+len(data):
                reads.append(addr);return int.from_bytes(data[addr-base:addr-base+16],'little')
        raise ValueError(f'out-of-region vector read {addr:x}')
    def combine(lo,hi): return ((q[hi]<<128)|q[lo])>>(sar*8)&((1<<128)-1)
    def mac(x,y):
        nonlocal acc
        xv=struct.unpack('<8h',q[x].to_bytes(16,'little'));yv=struct.unpack('<8h',q[y].to_bytes(16,'little'))
        acc=max(-(1<<39),min((1<<39)-1,acc+sum(x*y for x,y in zip(xv,yv))))
    for op,args in code:
        if op in ('entry','retw.n'): continue
        if op in ('movi','movi.n'): a[args[0]]=int(args[1],0)
        elif op=='ee.zero.accx': acc=0
        elif op in ('ee.vld.128.ip','ee.ld.128.usar.ip'):
            dest,ptr,step=args
            if op=='ee.ld.128.usar.ip': sar=a[ptr]&15
            q[dest]=load(a[ptr]);a[ptr]+=int(step)
        elif op=='ee.src.q':
            dest,lo,hi=args;q[dest]=combine(lo,hi)
        elif op=='ee.src.q.ld.ip':
            dest,ptr,step,lo,hi=args;v=combine(lo,hi);loaded=load(a[ptr]);q[lo]=v;q[dest]=loaded;a[ptr]+=int(step)
        elif op=='ee.vmulas.s16.accx': mac(*args)
        elif op=='ee.vmulas.s16.accx.ld.ip.qup':
            dest,ptr,step,x,y,lo,hi=args
            # Operands in this kernel do not alias any of the concurrent destinations.
            v=combine(lo,hi);loaded=load(a[ptr]);mac(x,y)
            q[dest]=loaded;q[lo]=v;a[ptr]+=int(step)
        elif op=='ee.srs.accx':
            dest,shift,zero=args
            assert zero=='0';acc >>= a[shift]&63;a[dest]=max(-(1<<31),min((1<<31)-1,acc))
        elif op in ('s32i','s32i.n'): stores[a[args[1]]+int(args[2])]=a[args[0]]
        else: raise ValueError('unsupported instruction '+op)
    return (stores[0x4000],stores[0x4004]),reads

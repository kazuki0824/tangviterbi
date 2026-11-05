"""TRM semantic model of the disassembled QACC kernel, not target execution."""
import struct

def execute(code, samples, coefficients):
    regions={0x1000:struct.pack('<'+'h'*len(samples),*samples),0x4000:struct.pack('<'+'h'*len(coefficients),*coefficients)}
    a={'a2':0x1000,'a3':0x4000,'a4':0x8000};q={f'q{j}':[0]*8 for j in range(8)};acc=[0]*8;out=bytearray([0xA5]*64);reads=[]
    def load(addr):
        addr&=~15
        for base,data in regions.items():
            if base<=addr and addr+16<=base+len(data):
                reads.append(addr);return struct.unpack('<8h',data[addr-base:addr-base+16])
        raise ValueError('vector read outside prepared table')
    def mac(x,y):
        for j in range(8): acc[j]=max(-(1<<39),min((1<<39)-1,acc[j]+q[x][j]*q[y][j]))
    for op,args in code:
        if op in ('entry','retw.n'): continue
        if op=='ee.zero.qacc': acc=[0]*8
        elif op=='addi':
            dest,src,imm=args;a[dest]=a[src]+int(imm)
        elif op=='ee.movi.32.a':
            src,dest,index=args;j=2*int(index);a[dest]=(q[src][j]&65535)|((q[src][j+1]&65535)<<16)
        elif op=='ee.movi.32.q':
            dest,src,index=args;j=2*int(index);v=list(q[dest]);word=a[src]
            v[j],v[j+1]=struct.unpack('<2h',word.to_bytes(4,'little'));q[dest]=v
        elif op=='ee.vld.128.ip':
            dest,ptr,step=args;q[dest]=load(a[ptr]);a[ptr]+=int(step)
        elif op=='ee.vmulas.s16.qacc':mac(*args)
        elif op=='ee.vmulas.s16.qacc.ld.ip':
            dest,ptr,step,x,y=args;mac(x,y);q[dest]=load(a[ptr]);a[ptr]+=int(step)
        elif op.startswith('ee.st.qacc_'):
            high=op.startswith('ee.st.qacc_h');part=op.split('.')[3]
            bits=sum((acc[j]&((1<<40)-1))<<(40*(j%4)) for j in range(4 if high else 0,8 if high else 4))
            width=16 if part=='l' else 4
            data=(bits&((1<<128)-1)).to_bytes(16,'little') if part=='l' else (bits>>128).to_bytes(4,'little')
            ptr,step=args;addr=a[ptr]&~(width-1);offset=addr-0x8000
            if not 0<=offset<=64-width:raise ValueError('output write outside buffer')
            out[offset:offset+width]=data;a[ptr]+=int(step)
        else:raise ValueError('unsupported '+op)
    values=[]
    for offset in (0,32):
        for j in range(4):values.append(int.from_bytes(out[offset+j*5:offset+j*5+5],'little',signed=True))
    return values,bytes(out),reads

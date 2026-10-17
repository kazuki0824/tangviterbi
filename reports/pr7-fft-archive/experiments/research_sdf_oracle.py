"""Independent radix-2 DIF fixed-point FFT reference for the research SDF RTL.

Inputs/outputs use signed Q15 pairs.  This is a reference *algorithm*, not an
SDF pipeline model: it operates on a whole in-memory array in DIF order.
Coefficient lookup is derived separately from the pinned hardware ROM table.
"""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
QUARTER=ROOT/"rtl/research_sdf_quarter_q16.hex"

def decode_word(w):
    a=w&65535
    b=(w>>16)&65535
    return (a if a<32768 else a-65536,b if b<32768 else b-65536)

def encode_word(a,b):
    assert -32768<=a<=32767 and -32768<=b<=32767
    return (a&65535)|((b&65535)<<16)

def bit_reverse(index, bits):
    return int(f"{index:0{bits}b}"[::-1],2)

def load_quarter():
    rows=[int(s,16) for s in QUARTER.read_text().split()]
    assert len(rows)==2048
    assert rows[0]==65536
    return rows

def coeff(phase,quarter):
    phase &= 8191
    q,off=divmod(phase,2048)
    ca=2048-off if q&1 else off
    sa=off if q&1 else 2048-off
    cr=0 if ca==2048 else quarter[ca]
    sr=0 if sa==2048 else quarter[sa]
    return (-cr if q in (1,2) else cr,
            -sr if q in (0,1) else sr)

def rounded_q16(x):
    return (x+32768)//65536 if x>=0 else -((-x+32768)//65536)

def saturate(x):
    return max(-32768,min(32767,x))

def reference_fft(words,quarter):
    n=len(words)
    assert n in (2048,4096,8192)
    a=[decode_word(w) for w in words]
    shift=n.bit_length()-2
    while shift>=0:
        d=1<<shift
        for base in range(0,n,2*d):
            for j in range(d):
                ar,ai=a[base+j]
                br,bi=a[base+j+d]
                sr,si=(ar+br)>>1,(ai+bi)>>1
                dr,di=(ar-br)>>1,(ai-bi)>>1
                wr,wi=coeff(j << (12-shift),quarter)
                yr=rounded_q16(dr*wr-di*wi)
                yi=rounded_q16(dr*wi+di*wr)
                a[base+j]=(sr,si)
                a[base+j+d]=(saturate(yr),saturate(yi))
        shift-=1
    return [encode_word(x,y) for x,y in a]

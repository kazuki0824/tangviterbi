"""Integer FFT oracle plus factorized frame transform; no RTL code reuse.

Samples signed 16-bit; twiddles signed 18-bit Q1.16, exact unity. Each radix2
stage divides by two. Round nearest, ties away; saturate rather than wrap.
Floating NumPy DFT is an additional independent numerical accuracy oracle.
"""
import math


def twiddle(phase,n):
    return (round(65536*math.cos(-2*math.pi*phase/n)),
            round(65536*math.sin(-2*math.pi*phase/n)))


def quantize(x,bits):
    value=(abs(x)+(1<<(bits-1)))>>bits
    if x<0:value=-value
    return max(-32768,min(32767,value)),not -32768<=value<=32767


def cross(x,w):
    r,rf=quantize(x[0]*w[0]-x[1]*w[1],16)
    i,inf=quantize(x[0]*w[1]+x[1]*w[0],16)
    return (r,i),rf or inf


def fft(samples):
    # Recursive decimation creates a differently structured oracle from the
    # RTL's in-place counters/bit-reversed load and memory address generation.
    if len(samples)==1:return list(samples),False
    even,ef=fft(samples[::2]);odd,of=fft(samples[1::2]);out=[None]*len(samples);fault=ef or of
    for j,(a,b) in enumerate(zip(even,odd)):
        wr,wi=twiddle(j,len(samples));tr=b[0]*wr-b[1]*wi;ti=b[0]*wi+b[1]*wr
        values=[]
        for x in (a[0]*65536+tr,a[1]*65536+ti,a[0]*65536-tr,a[1]*65536-ti):
            v,f=quantize(x,17);values.append(v);fault|=f
        out[j]=tuple(values[:2]);out[j+len(samples)//2]=tuple(values[2:])
    return out,fault


def frame(samples,tile_transform=None,cross_transform=None):
    n=len(samples);a,b={2048:(32,64),4096:(64,64),8192:(64,128)}[n]
    transform=tile_transform or (lambda jobs:[fft(x)[0] for x in jobs])
    first=transform([[samples[n1+a*n2] for n2 in range(b)] for n1 in range(a)])
    products=[(first[n1][k2],twiddle(n1*k2,n)) for k2 in range(b) for n1 in range(a)]
    middle=cross_transform(products) if cross_transform else [cross(x,w)[0] for x,w in products]
    second=transform([middle[k2*a:(k2+1)*a] for k2 in range(b)])
    return [second[k2][k1] for k1 in range(a) for k2 in range(b)]

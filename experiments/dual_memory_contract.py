"""Lossless T time-deinterleaver layout audit; no claim of receiver adoption.

ARIB STD-B31 v2.2-E1 section 3.11.1: m=(5*i)%96, per-layer I.
Receiver complements the transmitter delay: d=I*(95-m).
All carriers use six independent 8-bit LLRs. Zero-delay groups bypass SDRAM.
Read-before-write rings use d slots, never overwrite before read completion.
The grouped layouts can merge different layers ONLY when their actual delay
is equal. Frequency deinterleaving/reorder and their storage are NOT free.
"""
import argparse
from collections import defaultdict
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path

OTHER_BYTES = 155904 + 131072 + 65536 + 262144
CAPACITY = 8 * 1024**2
S_CW_RATE = Fraction(28860000, 203*4)


def groups(mode, layers):
    if mode not in (1, 2, 3):
        raise ValueError('mode')
    r = 1 << (mode-1)
    if not 1 <= len(layers) <= 3 or sum(s for s, _ in layers) != 13:
        raise ValueError('one to three layers, 13 segments')
    result = defaultdict(int)
    for segments, length in layers:
        if segments <= 0 or length not in (0, 4//r, 8//r, 16//r):
            raise ValueError('invalid layer')
        for i in range(96*r):
            result[length*(95-(5*i)%96)] += segments*6
    return dict(sorted(result.items()))


def audit(mode, layers, layout):
    g = groups(mode, layers)
    period = Fraction(2079, 8)*(1 << (mode-1))  # microseconds
    padded = compact = traffic = Fraction(0)
    group_count = 0
    for delay, size in g.items():
        if not delay:
            continue
        group_count += 1
        padded += delay*((size+31)//32)*32
        compact += ((delay*size+31)//32)*32
        if layout == 'aligned_group':
            traffic += 2*((size+31)//32)*32
        elif layout == 'compact_group_masked':
            # Exact ring-offset average, including partial first/last BL8.
            # Requires byte masks end-to-end (current integrated port lacks them).
            traffic += Fraction(sum(2*32*((k*size%32+size+31)//32)
                                    for k in range(delay)), delay)
        elif layout == 'carrier_padded':
            traffic += 2*32*(size//6)
        else:
            raise ValueError('layout')
    storage = int(compact if layout == 'compact_group_masked' else padded)
    if layout == 'carrier_padded':
        storage = sum(d*(n//6)*32 for d,n in g.items())
    # Capture/output + four FFT DMA transfers = six Q15 complex frames.
    fft = Fraction(6*4*(1 << (mode+10)), 1)/period
    # Individually aligned 204-byte codewords: seven BL8 each direction.
    s = S_CW_RATE*448/1000000
    total = fft + traffic/period + s + 10
    # Universal optimistic controller ceiling: >= 12 memory cycles/request.
    # No refresh, row misses, arbiter or CDC overhead included. This is an
    # upper bound, not a guaranteed service rate. Violating it proves rejection.
    ceiling = Fraction(135*32, 12)
    return dict(mode=mode, layers=layers, layout=layout,
                group_count=group_count, period_us=float(period),
                T_bus_MBps=float(traffic/period), S_bus_MBps=float(s),
                FFT_bus_MBps=float(fft), total_bus_MBps=float(total),
                T_ring_bytes=storage, other_reserved_bytes=OTHER_BYTES,
                total_reserved_bytes=storage+OTHER_BYTES,
                capacity_slack_bytes=CAPACITY-storage-OTHER_BYTES,
                optimistic_service_MBps=float(ceiling),
                overload_growth_min_bytes_per_ms=float(max(0, total-ceiling)*1000),
                capacity_pass=storage+OTHER_BYTES<=CAPACITY,
                optimistic_rate_pass=total<=ceiling,
                implemented=False, adopted=False)


def report():
    witnesses=[]
    for mode in (1,2,3):
        r=1 << (mode-1)
        for layers in ([(13,16//r)], [(1,4//r),(1,8//r),(11,16//r)]):
            for layout in ('carrier_padded','aligned_group','compact_group_masked'):
                witnesses.append(audit(mode,layers,layout))
    # All positive ordered segment partitions into <=3 layers, all legal I.
    extrema=[]
    for mode in (1,2,3):
        r=1 << (mode-1); cases=[]
        for count in (1,2,3):
            for cuts in itertools.combinations(range(1,13),count-1):
                edges=(0,)+cuts+(13,)
                segments=[b-a for a,b in zip(edges,edges[1:])]
                for lengths in itertools.product((0,4//r,8//r,16//r),repeat=count):
                    cases.append(audit(mode,list(zip(segments,lengths)),'aligned_group'))
        extrema.append(dict(mode=mode,case_count=len(cases),
                            capacity_fail_count=sum(not x['capacity_pass'] for x in cases),
                            max_capacity=max(cases,key=lambda x:x['total_reserved_bytes']),
                            max_traffic=max(cases,key=lambda x:x['total_bus_MBps'])))
    return dict(source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                specification='ARIB STD-B31 v2.2-E1 3.11.1, Tables 3-12 and 3-30',
                scope='Address/storage/BL8 demand audit. Necessary conditions only; no WCET or FIFO bound.',
                witnesses=witnesses,aligned_group_all_config_extrema=extrema)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.write_text(json.dumps(report(),indent=2)+'\n')

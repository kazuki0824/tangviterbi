"""Generate a finite cached-history QACC layout, not all possible SIMD layouts.
History is interleaved I16/Q16 (unscaled signed10); coefficients are tap-major
and reversed in tap order relative to newest-first reference. Four outputs.
Cache 16-tap tiles plus the output-window span in q0..q5; gather q6 via AR;
q7 holds coefficients. No tap-major IQ array, no output rounding.
"""
from collections import Counter

def patterns(up,down):
    import math
    groups=up//math.gcd(up,4)
    return Counter(tuple((4*b+j)*down//up-(4*b)*down//up for j in range(4)) for b in range(groups))

def symbol(k,offsets): return 's3_fir_reg_'+str(k)+'_'+''.join(map(str,offsets))

def generate(k,offsets):
    name=symbol(k,offsets);blocks=(16+max(offsets)+3)//4
    assert blocks<=6 and k in (16,32)
    lines=['.text','.align 4','.global '+name,'.type '+name+',@function',name+':','entry a1, 32','ee.zero.qacc','ee.vld.128.ip q7, a3, 16']
    for tile in range(k//16):
        if tile:lines.append(f'addi a2, a2, {64-blocks*16}')
        lines += [f'ee.vld.128.ip q{r}, a2, 16' for r in range(blocks)]
        for t in range(16):
            for lane,offset in enumerate(offsets):
                index=t+offset
                lines += [f'ee.movi.32.a q{index//4}, a5, {index%4}',f'ee.movi.32.q q6, a5, {lane}']
            if tile*16+t==k-1:lines.append('ee.vmulas.s16.qacc q6, q7')
            else:lines.append('ee.vmulas.s16.qacc.ld.ip q7, a3, 16, q6, q7')
    lines += ['ee.st.qacc_l.l.128.ip a4, 16','ee.st.qacc_l.h.32.ip a4, 16','ee.st.qacc_h.l.128.ip a4, 16','ee.st.qacc_h.h.32.ip a4, 16','retw.n','.size '+name+', .-'+name]
    return '\n'.join(lines)+'\n'

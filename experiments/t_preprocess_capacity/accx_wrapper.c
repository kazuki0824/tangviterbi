#include "accx_wrapper.h"
#include <string.h>

_Static_assert(_Alignof(accx_t_state) >= 16, "history alignment");
_Static_assert(offsetof(accx_t_state,q) % 16 == 0, "Q alignment");
_Static_assert(32 * 512 * 32768 < INT32_MAX - 256, "exact sum and rounding");

void accx_t_init(accx_t_state *s) { memset(s, 0, sizeof(*s)); }

/* GCC/Xtensa implements arithmetic right shift of negative signed integers. */
static inline int16_t q15(int32_t acc) {
    int32_t v = (acc + 256) >> 9;
    if (v > INT16_MAX) v = INT16_MAX;
    if (v < INT16_MIN) v = INT16_MIN;
    return (int16_t)v;
}

size_t accx_t_process(accx_t_state *restrict s,
                      const uint32_t *restrict src, size_t count,
                      const int16_t *restrict coeff,
                      int16_t *restrict out) {
    uint32_t head=s->head, phase=s->phase, skip=s->skip;
    int16_t *start=out;
    for (size_t n=0; n<count; ++n) {
        uint32_t w=src[n];
        int16_t i=(int16_t)((int32_t)(w<<22)>>22);
        int16_t q=(int16_t)((int32_t)(w<<12)>>22);
        head=(head-1u)&31u;
        s->i[head]=i; s->i[head+32]=i;
        s->q[head]=q; s->q[head+32]=q;
        if (skip) { skip=0; continue; }
        int32_t sums[2];
        s3_fir_accx_32(s->i+head, s->q+head, coeff+phase*32, sums);
        out[0]=q15(sums[0]); out[1]=q15(sums[1]); out+=2;
        skip=phase!=0;
        phase=(phase+31u)&31u;
    }
    s->head=head; s->phase=phase; s->skip=skip;
    return (size_t)(out-start)/2;
}

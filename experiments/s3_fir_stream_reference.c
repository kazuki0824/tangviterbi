#include "s3_fir_stream_reference.h"
#include <limits.h>
#include <string.h>
/* 33 * max|signed10| * max|signed16| = 553648128 < INT32_MAX.
 * Every partial sum also satisfies this bound; no int64 MAC is required. */
_Static_assert(INT32_MAX >= 553648128, "32-bit accumulator required");
static int16_t decode(uint32_t x) { return (int16_t)((int32_t)((x & 1023u)^512u)-512); }
int s3_fir_stream_init(s3_fir_stream *s, uint32_t up, uint32_t down, uint32_t taps) {
    if (!s || !up || down < up || down > UINT32_MAX-up || !taps || taps>33) return 0;
    memset(s,0,sizeof(*s)); s->up=up; s->down=down; s->taps=taps;
    return 1;
}
int s3_fir_stream_push(s3_fir_stream *s, uint32_t word, const int16_t *coeff,
                       int32_t *oi, int32_t *oq) {
    s->i[s->head]=decode(word); s->q[s->head]=decode(word>>10);
    uint32_t newest=s->head;
    if (++s->head==s->taps) s->head=0;
    if (s->skip) { --s->skip; return 0; }
    const int16_t *c=coeff+(size_t)s->phase*s->taps;
    int32_t a=0,b=0;
    for (uint32_t k=0;k<s->taps;++k) {
        a+=(int32_t)s->i[newest]*c[k]; b+=(int32_t)s->q[newest]*c[k];
        newest=newest ? newest-1 : s->taps-1;
    }
    *oi=a; *oq=b;
    uint32_t next=s->phase+s->down;
    s->skip=next/s->up-1; s->phase=next%s->up;
    return 1;
}

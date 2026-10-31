#ifndef S3_IQ10_INLINE_H
#define S3_IQ10_INLINE_H
#include <stdint.h>
/* Experimental inline candidate; not the default kernel.
 * Internal shared primitive: caller guarantees 4-byte destination alignment,
 * eight contiguous source words, and 20 contiguous destination bytes.
 * S3_HOT is supplied by each translation unit. */
static inline S3_HOT __attribute__((always_inline)) void pack_eight(uint8_t *dst, const uint32_t *src)
{
    const uint32_t a=src[0]&0xfffffu, b=src[1], c=src[2]&0xfffffu, d=src[3];
    const uint32_t e=src[4], f=src[5]&0xfffffu, g=src[6], h=src[7];
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    // s3_ring_init_split enforces four-byte page alignment; this helper is
    // entered only at a four-byte offset. may_alias preserves the character
    // buffer's C aliasing contract while avoiding a 20-byte temporary memcpy.
    typedef uint32_t alias_word __attribute__((may_alias));
    alias_word *out = (alias_word *)(void *)dst;
    out[0]=a|(b<<20);
    out[1]=((b>>12)&255u)|(c<<8)|(d<<28);
    out[2]=((d>>4)&65535u)|(e<<16);
    out[3]=((e>>16)&15u)|(f<<4)|(g<<24);
    out[4]=((g>>8)&4095u)|(h<<12);
#else
    const uint32_t w[5]={a|(b<<20), ((b>>12)&255u)|(c<<8)|(d<<28), ((d>>4)&65535u)|(e<<16),
                          ((e>>16)&15u)|(f<<4)|(g<<24), ((g>>8)&4095u)|(h<<12)};
    for (unsigned i=0;i<20;++i) dst[i]=(uint8_t)(w[i/4]>>(8*(i%4)));
#endif
}

#endif

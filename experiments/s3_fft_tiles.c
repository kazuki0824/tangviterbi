#include "s3_fft_tiles.h"
#include <limits.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#define S3_FFT_HOT IRAM_ATTR
#else
#define S3_FFT_HOT
#endif

static S3_FFT_HOT int16_t rounded_q16(int64_t value)
{
    // Round to nearest, ties away from zero; avoid negative signed shifts.
    int64_t q = value >= 0 ? (value + 32768) / 65536 : -((-value + 32768) / 65536);
    if (q > INT16_MAX) q = INT16_MAX;
    if (q < INT16_MIN) q = INT16_MIN;
    return (int16_t)q;
}

void S3_FFT_HOT s3_fft_reverse_tile(int16_t *data, unsigned n, unsigned begin, unsigned end)
{
    unsigned bits = 0;
    for (unsigned value = n; value > 1; value >>= 1) ++bits;
    for (unsigned i = begin; i < end; ++i) {
        unsigned j = 0, value = i;
        for (unsigned bit = 0; bit < bits; ++bit) { j = 2*j + (value & 1); value >>= 1; }
        // The smaller index owns BOTH elements. The other core cannot write
        // either element via the reversed index, including across tile edges.
        if (i < j) {
            int16_t r = data[2*i], q = data[2*i+1];
            data[2*i] = data[2*j]; data[2*i+1] = data[2*j+1];
            data[2*j] = r; data[2*j+1] = q;
        }
    }
}

void S3_FFT_HOT s3_fft_stage_tile(int16_t *data, const int16_t *twiddle, unsigned n,
                       unsigned span, unsigned begin, unsigned end)
{
    unsigned half = span / 2;
    for (unsigned id = begin; id < end; ++id) {
        unsigned j = id % half, a = (id / half) * span + j, b = a + half;
        unsigned w = j * (n / span);
        int64_t ar = (int64_t)data[2*a] * 32768, ai = (int64_t)data[2*a+1] * 32768;
        int64_t br = (int64_t)data[2*b] * twiddle[2*w] - (int64_t)data[2*b+1] * twiddle[2*w+1];
        int64_t bi = (int64_t)data[2*b] * twiddle[2*w+1] + (int64_t)data[2*b+1] * twiddle[2*w];
        // Fixed FFT scaling 1/2 per stage, hence 1/n overall. This is the
        // numerical FFT contract; it does not shrink the transferred bin set.
        data[2*a] = rounded_q16(ar + br); data[2*a+1] = rounded_q16(ai + bi);
        data[2*b] = rounded_q16(ar - br); data[2*b+1] = rounded_q16(ai - bi);
    }
}

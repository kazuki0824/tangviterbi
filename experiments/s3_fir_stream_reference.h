#ifndef S3_FIR_STREAM_REFERENCE_H
#define S3_FIR_STREAM_REFERENCE_H
#include <stddef.h>
#include <stdint.h>
/* Exact streaming reference, not a target SIMD/WCET implementation.
 * Fixed K taps per phase, coefficient[p*K+k] multiplies x[newest-k].
 * Zero initial history; output m is at input floor(m*M/L), phase m*M%L.
 * L <= M (at most one output per input), K <= 33. No output quantization.
 */
typedef struct {
    int16_t i[33], q[33];
    uint32_t up, down, taps, phase, skip, head;
} s3_fir_stream;
int s3_fir_stream_init(s3_fir_stream *s, uint32_t up, uint32_t down, uint32_t taps);
/* Returns 1 if an output was produced, 0 otherwise. Valid initialized s and
 * nonaliasing coefficient/output pointers required; consumes exactly one word. */
int s3_fir_stream_push(s3_fir_stream *s, uint32_t word, const int16_t *coeff,
                       int32_t *oi, int32_t *oq);
#endif

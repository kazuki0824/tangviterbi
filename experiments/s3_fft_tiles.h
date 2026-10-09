#ifndef S3_FFT_TILES_H
#define S3_FFT_TILES_H
#include <stdint.h>

/* Functional Q15 reference tiles, NOT the S3 SIMD kernel or a WCET claim.
 * Caller validates power-of-two n>=2, span in [2,n], and non-overlapping tiles.
 * data is n interleaved complex values; twiddle is n/2 complex values (2*n B).
 * Complete bit reversal before the first stage. Barrier between every stage.
 * Within each phase tiles may run on either core in any order.
 */
void s3_fft_reverse_tile(int16_t *data, unsigned n, unsigned begin, unsigned end);
void s3_fft_stage_tile(int16_t *data, const int16_t *twiddle, unsigned n,
                       unsigned span, unsigned begin, unsigned end);
#endif

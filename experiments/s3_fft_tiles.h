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
/* Same exact Q15 coefficients using n/4+1 unsigned sine magnitudes, including
 * 32768 at pi/2. Caller supplies round(32768*sin(2*pi*k/n)), 0<=k<=n/4.
 * n is a power of two >=4. No bin/sample reduction; scalar, no WCET claim. */
void s3_fft_quarter_pair(const uint16_t *quarter, unsigned n, unsigned w,
                         int16_t *real, int16_t *imag);
void s3_fft_stage_quarter_tile(int16_t *data, const uint16_t *quarter, unsigned n,
                              unsigned span, unsigned begin, unsigned end);
#endif

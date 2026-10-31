#ifndef S3_FIR_QACC_PREPARE_H
#define S3_FIR_QACC_PREPARE_H
#include <stddef.h>
#include <stdint.h>
/* Reference gather, not a speed-qualified implementation. Phase-major coeff.
 * i/q are decoded signed10 history indexed from stream start, zero before 0.
 * Four outputs starting at first_output; size must cover their newest samples.
 * out_samples/out_coeff have room for taps*8 int16, disjoint from all inputs.
 * Assembly additionally needs 16-byte alignment on these output buffers.
 * Returns 0 before any output write if scalar arguments are invalid.
 */
int s3_fir_qacc_prepare(const int16_t *i, const int16_t *q, size_t size,
    const int16_t *coeff, uint32_t up, uint32_t down, uint32_t taps,
    uint32_t first_output, int16_t *out_samples, int16_t *out_coeff);
void s3_fir_qacc_16(const int16_t *samples, const int16_t *coeff, uint8_t out[64]);
void s3_fir_qacc_32(const int16_t *samples, const int16_t *coeff, uint8_t out[64]);
#endif

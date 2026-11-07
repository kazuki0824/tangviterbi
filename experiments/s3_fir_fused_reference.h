#ifndef S3_FIR_FUSED_REFERENCE_H
#define S3_FIR_FUSED_REFERENCE_H
#include <stddef.h>
#include <stdint.h>
/* Comparison kernel, not a receiver or measured fast implementation.
 * words[k]: I signed10 in bits 0..9, Q signed10 in bits 10..19.
 * Upper 12 metadata bits are ignored, as in raw IQ packing.
 * coeff[k] corresponds to exactly words[k]; caller selects phase/history.
 * No intermediate I16/Q16 array and no rounding or requantization here.
 * All pointers valid, count <= 33, disjoint outputs; returns 0 on invalid input.
 */
int s3_fir_fused_reference(const uint32_t *words, const int16_t *coeff,
                         size_t count, int64_t *i_sum, int64_t *q_sum);
#endif

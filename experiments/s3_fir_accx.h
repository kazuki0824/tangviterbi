#ifndef S3_FIR_ACCX_H
#define S3_FIR_ACCX_H
#include <stdint.h>
/* ESP32-S3/windowed ABI; see .S for PIE context and readable-padding contract.
 * I/Q: contiguous signed10 samples held in int16, newest to oldest.
 * coeff: same order, 16-byte aligned; out: two int32, 4-byte aligned.
 * K/8+1 aligned history blocks are read, including padding outside K samples.
 * No pointer checks, phase scheduling, unpack, output scaling or saturation.
 */
void s3_fir_accx_16(const int16_t *i, const int16_t *q,
                    const int16_t *coeff, int32_t out[2]);
void s3_fir_accx_32(const int16_t *i, const int16_t *q,
                    const int16_t *coeff, int32_t out[2]);
#endif

#ifndef ACCX_T_WRAPPER_H
#define ACCX_T_WRAPPER_H
#include <stddef.h>
#include <stdint.h>

/* Trial CPU wrapper for the existing exact signed10 x signed16 ACCX kernel.
 * 32 taps, L/M=32/63. It is not integrated into the RF/RTOS/DMA receiver.
 * coeff[p*32+k] multiplies input[floor(m*63/32)-k], p=m*63%32.
 * Input words carry signed I10/Q10 in bits 0..9/10..19; metadata is ignored.
 * Output trial contract: Q15 coefficients and signed10 samples scaled to Q15;
 * round nearest, ties toward +infinity, then saturate to signed16. The actual
 * receiver's coefficient response and final rounding contract remain unproved.
 * All pointer regions must be nonaliasing. coeff must be 16-byte aligned and
 * cover 32*32 int16. out must fit count complex outputs (a safe upper bound).
 * State and its members have 16-byte alignment. Each 64-element plane contains
 * two identical copies of a reverse ring. Every aligned 5-vector kernel read
 * from head=0..31 stays wholly in that plane, including its extra padding load.
 * Caller/runtime must own PIE q0..q7, ACCX and SAR_BYTE while calling this.
 */
typedef struct {
    _Alignas(16) int16_t i[64];
    _Alignas(16) int16_t q[64];
    uint32_t head, phase, skip;
} accx_t_state;
void accx_t_init(accx_t_state *s);
size_t accx_t_process(accx_t_state *restrict s,
                      const uint32_t *restrict src, size_t count,
                      const int16_t *restrict coeff,
                      int16_t *restrict out);
void s3_fir_accx_32(const int16_t *i, const int16_t *q,
                    const int16_t *coeff, int32_t out[2]);
#endif

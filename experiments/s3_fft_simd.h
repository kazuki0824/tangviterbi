#ifndef S3_FFT_SIMD_H
#define S3_FFT_SIMD_H
#include <stdint.h>
#define S3_FFT_SIMD_POINTS 8192u
#define S3_FFT_SIMD_COEFFICIENT_BYTES 16384u
/* Pinned ESP-DSP v1.7.1 sc16 kernel, not the scalar tiles' rounding contract.
 * data is an exclusively owned 32768-byte frame, table is 16384 bytes. Both
 * must be 16-byte aligned, live and disjoint. No allocation or hidden copy.
 * On S3, this function requires core1 and internal data/coefficient SRAM;
 * it masks local interrupts around FFT/reordering to own the vector context.
 * RF poll/packing must remain on core0, and high-priority/NMI handlers must
 * not use PIE. The lock/IRQ policy still requires whole-system verification.
 * Do not assume a
 * WCET from the official 1024-point benchmark; cache/DMA/IRQ must be measured.
 * Output is all 8192 complex Q15 bins in natural order, scaled by 1/8192.
 */
enum { S3_FFT_SIMD_OK=0, S3_FFT_SIMD_POINTER=-1, S3_FFT_SIMD_OWNER=-2 };
typedef struct { uint32_t fft_cycles, reorder_cycles; } s3_fft_simd_measurement;
extern const int16_t s3_fft_simd_table[8192]; /* Flash rodata by default. */
int s3_fft_simd_run(int16_t *data, const int16_t *table, s3_fft_simd_measurement *measurement);
#endif

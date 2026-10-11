#ifndef S3_FFT_SIMD_TILES_H
#define S3_FFT_SIMD_TILES_H
#include <stdint.h>
/* 13 stages, each 1024 independent blocks of four complex butterflies.
 * Stage 0..10 use N2=4096..4, stage11 N2=2, stage12 N2=1.
 * Assign disjoint block ranges to the two cores and complete a barrier BEFORE
 * the next stage. Call RF poll between tiles and while waiting at barriers.
 * At most 16 blocks (64 butterflies) per call. No measured WCET is implied.
 * On S3 each call masks only its own core's interrupts for its short kernel;
 * high-priority/NMI handlers must not use PIE. data/table are internal SRAM,
 * 16-byte aligned, disjoint, and exclusively owned until the final stage.
 * Output stays in bit-reversed order: sample index i is FFT bin reverse13(i).
 * FPGA must apply this index mapping; all 8192 Q15 complex bins are preserved.
 */
int s3_fft_simd_tile(int16_t *data,const int16_t *table,unsigned stage,
                     unsigned block_begin,unsigned block_count);
#endif

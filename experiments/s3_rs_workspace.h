#ifndef S3_RS_WORKSPACE_H
#define S3_RS_WORKSPACE_H
#include "s3_rs_rpc.h"
/* The two 32 KiB FFT slots in the existing ROM-safe proposal are NOT
 * contiguous. Partition S-mode storage explicitly across those two slots.
 * DMA pages use 32-byte alignment; no overlay with the 64 KiB RF queue.
 * Caller may change T/S ownership only after all users/DMAs have stopped. */
typedef struct {
 s3_rs_rpc_context contexts[3];
 uint32_t crc[256];
 uint8_t rx[4096] __attribute__((aligned(32)));
 uint8_t tx[4096] __attribute__((aligned(32)));
} s3_rs_slot0;
typedef struct {
 s3_rs_rpc_context contexts[2];
 s3_rs_tables tables;
 /* A second RX/TX pair avoids requiring CPU page processing to finish
  * before the other direction's next DMA. Actual queue scheduling remains
  * a separate gate; these reservations alone do not prove overlap. */
 uint8_t rx[4096] __attribute__((aligned(32)));
 uint8_t tx[4096] __attribute__((aligned(32)));
} s3_rs_slot1;
typedef union __attribute__((aligned(32))) {
 uint8_t fft[32768];s3_rs_slot0 rs;
} s3_mode_slot0;
typedef union __attribute__((aligned(32))) {
 uint8_t fft[32768];s3_rs_slot1 rs;
} s3_mode_slot1;
extern const uint32_t s3_rs_workspace_layout[14];
void s3_rs_workspace_init(s3_mode_slot0 *a,s3_mode_slot1 *b);
s3_rs_rpc_context *s3_rs_workspace_context(s3_mode_slot0 *a,s3_mode_slot1 *b,unsigned index);
#endif

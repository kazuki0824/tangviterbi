#ifndef S3_RS_RPC_H
#define S3_RS_RPC_H
#include "s3_rs_offload.h"
#define S3_RS_RPC_PAGE 4096
#define S3_RS_RPC_BLOCKS 204
enum { S3_RS_RPC_SYNDROME=1, S3_RS_RPC_LAMBDA=2,
       S3_RS_RPC_ROOTS=3, S3_RS_RPC_MAGNITUDES=4 };
enum { S3_RS_RPC_FREE=0, S3_RS_RPC_WAIT_ROOTS=1, S3_RS_RPC_WAIT_ACK=2 };
typedef struct {
 uint32_t batch;
 uint16_t epoch;
 uint8_t phase,failed[S3_RS_RPC_BLOCKS];
 s3_rs_solution solution[S3_RS_RPC_BLOCKS];
} s3_rs_rpc_context;
/* Caller owns internal-SRAM tables, contexts and two DISTINCT DMA pages.
 * No allocation, no IO and no concurrency protection is hidden here.
 * The scheduler must supply the expected epoch/batch, retain the context
 * through confirmed response DMA completion, and stop the epoch on failure.
 * A retry is rejected; this protocol does not silently reuse stale work.
 * Reset is permitted only after outstanding IO has stopped and drained. */
void s3_rs_rpc_crc_init(uint32_t table[256]);
uint32_t s3_rs_rpc_crc(const uint32_t table[256],const uint8_t page[4096]);
void s3_rs_rpc_reset(s3_rs_rpc_context *context);
int s3_rs_rpc_syndromes(s3_rs_tables *tables,const uint32_t crc[256],
 s3_rs_rpc_context *context,uint16_t expected_epoch,uint32_t expected_batch,
 const uint8_t rx[4096],uint8_t tx[4096]);
int s3_rs_rpc_roots(s3_rs_tables *tables,const uint32_t crc[256],
 s3_rs_rpc_context *context,const uint8_t rx[4096],uint8_t tx[4096]);
int s3_rs_rpc_ack(s3_rs_rpc_context *context,uint16_t epoch,uint32_t batch);
#endif

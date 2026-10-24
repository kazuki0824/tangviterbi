#ifndef S3_PARALLEL_PACK_H
#define S3_PARALLEL_PACK_H
#include <stdbool.h>
#include <stdint.h>
#include <stdatomic.h>

enum { S3_PP_BANKS=3, S3_PP_WORDS=16384, S3_PP_CHUNK=32768, S3_PP_SLOTS=4 };
enum { S3_PP_OK, S3_PP_BUSY, S3_PP_EMPTY, S3_PP_INVALID, S3_PP_STALE,
       S3_PP_FAULT, S3_PP_DEADLINE, S3_PP_SEQUENCE };
typedef struct { atomic_uint state; unsigned begin, end, cursor; } s3_pp_job;
typedef struct {
 const uint32_t *words;
 uint64_t sequence, deadline, output;
 unsigned first, pairs; uint32_t prefix;
 bool has_prefix, owned;
 s3_pp_job jobs[2];
} s3_pp_bank;
typedef struct {
 uint8_t *buffers[S3_PP_SLOTS];
 s3_pp_bank banks[S3_PP_BANKS];
 unsigned fifo[S3_PP_BANKS], head, count;
 uint64_t next_sample, bank_sequence, reserved, published, submitted, retired;
 uint64_t dma_sequence[S3_PP_SLOTS];
 unsigned dma_state[S3_PP_SLOTS];
 uint32_t carry; bool have_carry;
 atomic_uint fault;
} s3_parallel_pack;
/* Initialize only while RF, both workers and SPI DMA are stopped.
 * Four disjoint 32-KiB arenas, each >=4-byte aligned; no payload copy/heap here.
 * Coordinator alone calls accept/collect/reclaim/take/complete.
 * Exactly one caller per worker ID calls step; these two callers may overlap.
 * Hardware must finish writing a source bank before accept. Reclaim is the
 * mandatory gate BEFORE sentinel writes/RF reuse. On fault stop RF and quiesce
 * both workers + SPI before reinitializing. Fault does NOT cancel live DMA.
 */
int s3_pp_init(s3_parallel_pack*, uint8_t *const buffers[4]);
int s3_pp_accept(s3_parallel_pack*, unsigned bank, const uint32_t *words,
 unsigned first, unsigned count, uint64_t first_sample, uint64_t now, uint64_t deadline);
/* now/deadline/bound use ONE validated common clock across cores, not unrelated
 * per-core counters. bound includes all source reads in this bounded slice.
 * Caller must interleave RF polling and supply measured WCET; not proved here.
 */
int s3_pp_step(s3_parallel_pack*, unsigned worker, unsigned max_pairs,
 uint64_t now, uint64_t bound, unsigned *processed);
/* A monotonic, cross-core common clock in the same epoch/units as accept's
 * deadline. Its reads and quantization error must be included in bound.
 * Clocked step checks the post-read timestamp before publishing DONE.
 * This sampled interval excludes callback return/publication overhead; it is
 * not a measurement of the entire function WCET. Fault retains
 * source/payload ownership; no automatic retry or buffer reuse is allowed.
 * The legacy step above trusts the supplied bound; it does not measure time.
 */
typedef uint64_t (*s3_pp_clock)(void*);
int s3_pp_step_clocked(s3_parallel_pack*, unsigned worker, unsigned max_pairs,
 s3_pp_clock, void *clock_ctx, uint64_t bound, unsigned *processed);
int s3_pp_collect(s3_parallel_pack*, uint64_t now);
int s3_pp_reclaim(s3_parallel_pack*, unsigned bank);
/* take leases one full contiguous 32-KiB payload. complete ONLY after SPI reap.
 * Complete may be out of order; physical storage is reused only after a
 * contiguous completed prefix. BUSY/EMPTY do not consume/drop input/output.
 */
int s3_pp_take(s3_parallel_pack*, uint64_t *sequence, const uint8_t **payload);
int s3_pp_complete(s3_parallel_pack*, uint64_t sequence);
#endif

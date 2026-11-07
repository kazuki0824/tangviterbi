#ifndef T_NATIVE_ADAPTER_H
#define T_NATIVE_ADAPTER_H
#include "halfband_pipeline.h"
#include "s3_native_capture.h"
#include <stdbool.h>

/* Reconstruction v2: this header was not recovered byte-for-byte. The three
 * recovered implementation files use these named fields and interfaces. The
 * target build, rather than the historical size, defines the new RAM ledger.
 * One core0 owner serializes sink callbacks and step. Initialize to zero;
 * init/reinit is permitted only with RF off, no retained input and no live
 * pipeline/output lease. Native input words retain all 32 bits until unpack.
 */
enum { HBNATIVE_OK = 0, HBNATIVE_EMPTY = 1, HBNATIVE_BUSY = 2,
       HBNATIVE_NEED_OUTPUT = 3, HBNATIVE_INVALID = 4, HBNATIVE_FAILED = 5 };
enum { HBNATIVE_FAULT_NONE = 0, HBNATIVE_FAULT_ARGUMENT = 1,
       HBNATIVE_FAULT_RECLAIM = 2, HBNATIVE_FAULT_SEQUENCE = 3,
       HBNATIVE_FAULT_DEADLINE = 4, HBNATIVE_FAULT_PIPE = 5,
       HBNATIVE_FAULT_BOUND = 6, HBNATIVE_FAULT_CLOCK = 7,
       HBNATIVE_FAULT_OVERFLOW = 8 };
typedef struct {
    const uint32_t *words;
    uint64_t deadline, first_sample;
    unsigned first, count, consumed;
    bool owned;
} hbnative_bank;
typedef struct {
    _Alignas(16) uint32_t carry[HBPIPE_RAW];
    hbpipe *pipe;
    hbnative_bank banks[S3_CAPTURE_BANKS];
    unsigned fifo[S3_CAPTURE_BANKS], head, count, fill, epoch, fault;
    uint64_t next_sample, consumed_samples, produced_samples, last_time;
} hbnative;
typedef struct {
    unsigned consumed, copied, produced;
    uint32_t sequence;
    uint64_t first_sample;
} hbnative_result;

int hbnative_init(hbnative *, hbpipe *, uint32_t epoch);
size_t hbnative_size(void);
unsigned hbnative_fault(const hbnative *);
unsigned hbnative_pending_words(const hbnative *);
s3_native_sink hbnative_sink(hbnative *);
/* At most max_words <=1024 source words and one output block per call. The
 * caller reserves output independently of workspace and keeps it reserved
 * after publication, including post-publication failures. A source bank may
 * be reclaimed only after synchronous read/copy has finished. A partial tail
 * is retained, never padded or discarded. bound is a declared admission upper
 * bound, not a measured lower bound; clock_error < bound, in 240 MHz cycles.
 */
int hbnative_step_clocked(hbnative *, int16_t *output, unsigned max_words,
                        s3_native_clock, void *clock_ctx, uint32_t clock_error,
                        uint32_t bound, hbnative_result *);
#endif

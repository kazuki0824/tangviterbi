#ifndef TPRE_RUNTIME_H
#define TPRE_RUNTIME_H
#include "native_adapter.h"
#include <stdatomic.h>

/* One core0 owner; one core1 hbpipe worker. All fields except stop/fault and
 * hbpipe publication belong to core0. The same C owner is used by the host
 * event harness and the SDK tasks. Each call advances one bounded phase. */
enum { TPRE_FRAME_BYTES=16384, TPRE_FRAMES=8, TPRE_BLOCKS_PER_FRAME=8,
       TPRE_BLOCK_BYTES=2048, TPRE_QUEUE_DEPTH=2, TPRE_PHASES=9 };
#ifndef TPRE_PREPARE_WORDS_PER_ITERATION
#define TPRE_PREPARE_WORDS_PER_ITERATION 2048
#endif
_Static_assert(TPRE_PREPARE_WORDS_PER_ITERATION==1024||TPRE_PREPARE_WORDS_PER_ITERATION==2048,
               "only the audited diagnostic and candidate prepare budgets");
enum { TPRE_FREE=0, TPRE_FILLING=1, TPRE_READY=2, TPRE_DMA=3 };
enum { TPRE_OK=0, TPRE_IDLE=1, TPRE_ERROR=2 };
enum { TPRE_OP_POLL=1, TPRE_OP_REAP, TPRE_OP_PRODUCE, TPRE_OP_DMA_REAP,
       TPRE_OP_DMA_SUBMIT, TPRE_OP_FEED, TPRE_OP_WORK, TPRE_OP_STOP };
typedef struct {
    unsigned operation, phase, result, words, copied, produced;
    uint32_t sequence;
    uint64_t first_sample;
} tpre_event;
typedef struct {
    void *ctx;
    /* submit: only called when runtime owns a complete frame and queue room.
     * Any error is fatal and retains the DMA lease, even before HW acceptance.
     * reap: 0=one exact ordered completion; 1=no completion; 2=fatal. */
    int (*submit)(void *, unsigned epoch, uint32_t sequence, const void *, unsigned);
    int (*reap)(void *, uint32_t *sequence);
    bool (*feed)(void *, unsigned core);
} tpre_io;
typedef struct {
    uint8_t *data;
    uint32_t sequence;
    unsigned state, reserved, completed;
} tpre_frame;
typedef struct {
    hbpipe *pipeline;
    hbnative *native;
    s3_native_capture *capture;
    s3_native_clock clock;
    void *clock_ctx;
    uint32_t clock_error;
    uint32_t step_bound;
    tpre_io io;
    tpre_frame frames[TPRE_FRAMES];
    uint32_t block_next, block_reap, submit_next, complete_next;
    unsigned epoch, phase, prepare_words, dma_count;
    atomic_uint stop, fault;
} tpre_runtime;

/* RF off and worker stopped. Caller owns all 8 disjoint, 16-byte aligned
 * internal DMA frames and objects for the complete run, drain and task death.
 * Epoch must match hbnative_init and SDK queue_open; no in-place epoch change.
 * An epoch ends before 32-bit FPGA byte-offset wrap. */
bool tpre_init(tpre_runtime *, hbpipe *, hbnative *, s3_native_capture *,
              uint8_t *const frames[TPRE_FRAMES], unsigned epoch,
              s3_native_clock, void *clock_ctx, uint32_t clock_error,
              uint32_t step_bound, tpre_io);
int tpre_owner_step(tpre_runtime *, tpre_event *);
int tpre_worker_step(tpre_runtime *, tpre_event *);
void tpre_request_stop(tpre_runtime *);
bool tpre_stopping(const tpre_runtime *);
size_t tpre_size(void);
#endif

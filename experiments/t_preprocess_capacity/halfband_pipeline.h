#ifndef HALFBAND_PIPELINE_H
#define HALFBAND_PIPELINE_H
#include "halfband31.h"
#include <stdatomic.h>

/* Fixed-block CPU candidate, not a native-RF/SDK receiver adapter. One producer
 * on core0 and one consumer on core1. No task may reenter its own operation.
 * Both cores must own their PIE context while calling the FIR primitive.
 * After successful init, callers do not mutate shift or structural fields
 * while either core is active; only the documented per-core API is used.
 */
enum { HBPIPE_RAW = 1024, HBPIPE_OUTPUT = 512, HBPIPE_SLOTS = 2,
       HBPIPE_CORE0_OUTPUT = 32 };
enum { HBPIPE_FREE = 0, HBPIPE_READY = 1, HBPIPE_DONE = 2 };
enum { HBPIPE_OK = 0, HBPIPE_EMPTY = 1, HBPIPE_BUSY = 2,
       HBPIPE_INVALID = 3, HBPIPE_ORDER = 4 };
typedef struct {
    hb31_workspace workspace;
    atomic_uint status;
    uint32_t sequence;
    int16_t *output;
} hbpipe_slot;
typedef struct {
    hb31_state history;                 /* producer only */
    uint32_t produce_next, consume_next, reap_next, shift;
    hbpipe_slot slots[HBPIPE_SLOTS];
} hbpipe;

/* init is RF-off only, with no live worker, workspace or DMA lease. The caller
 * supplies a 16-byte aligned hbpipe. shift has the primitive's 0..31 contract.
 */
int hbpipe_init(hbpipe *, uint32_t shift);
size_t hbpipe_size(void);

/* core0: raw[1024] is 4-byte aligned, disjoint from this hbpipe, and readable
 * until this call returns.
 * output[1024] is 16-byte aligned, externally reserved writable DMA storage.
 * It may not alias raw, this hbpipe, another live output or a DMA-owned region.
 * The external arena owner is responsible for that lease check. No raw copy
 * survives the call: history is copied forward before READY is published.
 * BUSY/INVALID changes neither history, output, slot nor sequence counters.
 */
int hbpipe_produce(hbpipe *, const uint32_t *raw, int16_t *output);

/* core1: consumes exactly the next READY slot. No producer history accesses.
 * DONE release makes all output stores visible to the core0 reaper.
 */
int hbpipe_work(hbpipe *);

/* core0: returns one completed output and sequence, then releases WORKSPACE.
 * This does not release OUTPUT. Its external DMA lease lasts until transfer
 * completion. Eight successive 2048-byte outputs can fill one 16KiB frame;
 * submit only after all eight are reaped, never while either CPU can write it.
 */
int hbpipe_reap(hbpipe *, int16_t **output, uint32_t *sequence);
unsigned hbpipe_status(const hbpipe *, unsigned slot);
#endif

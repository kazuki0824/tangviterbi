#ifndef S3_CAPTURE_BRIDGE_H
#define S3_CAPTURE_BRIDGE_H
#include "s3_transport.h"
enum { S3_CAPTURE_BANKS = 3, S3_CAPTURE_WORDS = 16384 };
enum s3_capture_fault { S3_CAPTURE_GOOD, S3_CAPTURE_SEQUENCE, S3_CAPTURE_RECLAIM,
                        S3_CAPTURE_DEADLINE, S3_CAPTURE_ARGUMENT };
typedef struct {
    const uint32_t *words;
    uint64_t deadline;
    uint32_t first, count, consumed;
    bool owned;
} s3_capture_bank;
typedef struct {
    s3_iq10_packer packer;
    s3_capture_bank banks[S3_CAPTURE_BANKS];
    unsigned fifo[S3_CAPTURE_BANKS], head, count;
    uint64_t next_sample, consumed_samples;
    enum s3_capture_fault fault;
} s3_capture_bridge;
void s3_capture_init(s3_capture_bridge *b, s3_tx_ring *ring);
/* Called after RF bank switch and exact sentinel-boundary validation.
 * The caller's deadline is BEFORE any sentinel write or RF reuse of this
 * bank. All calls are serialized by one owner; no ISR edits this object.
 */
bool s3_capture_accept(s3_capture_bridge *b, unsigned bank, const uint32_t *words,
                       unsigned first, unsigned count, uint64_t first_sample,
                       uint64_t now, uint64_t deadline);
/* Call before clearing sentinels/selecting a bank. False requires stopping
 * the RF writer and reporting a discontinuity, NEVER silently abandoning IQ.
 */
bool s3_capture_reclaim(s3_capture_bridge *b, unsigned bank);
/* Performs a bounded number of source-word consumptions. caller supplies a
 * validated worst-case slice budget in the same extended core-clock units.
 * False means a latched fault. Ring backpressure is a successful zero step.
 */
bool s3_capture_step(s3_capture_bridge *b, unsigned max_words, uint64_t now,
                     uint32_t slice_bound, unsigned *consumed);
#endif

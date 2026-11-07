#include "native_adapter.h"
#include <limits.h>
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#define HOT IRAM_ATTR
#else
#define HOT
#endif
#define AUDIT __attribute__((noinline))

_Static_assert(S3_CAPTURE_BANKS == 3, "bounded three-bank native FIFO");
_Static_assert(S3_CAPTURE_WORDS == 16384, "native ring mask");

static bool HOT hbnative_fail(hbnative *a, unsigned reason) {
    if (a && !a->fault) a->fault = reason;
    return false;
}

int hbnative_init(hbnative *a, hbpipe *p, uint32_t epoch) {
    if (!a || !p || ((uintptr_t)a & 15u) || ((uintptr_t)p & 15u) ||
        !epoch || epoch > UINT16_MAX || p->shift > 31u ||
        p->produce_next || p->consume_next || p->reap_next)
        return HBNATIVE_INVALID;
    if (a->count || a->fill) return HBNATIVE_INVALID;
    for (unsigned n = 0; n < HBPIPE_SLOTS; ++n)
        if (hbpipe_status(p, n) != HBPIPE_FREE || p->slots[n].output)
            return HBNATIVE_INVALID;
    memset(a, 0, sizeof(*a));
    a->pipe = p;
    a->epoch = epoch;
    return HBNATIVE_OK;
}

size_t hbnative_size(void) { return sizeof(hbnative); }
unsigned HOT hbnative_fault(const hbnative *a) {
    return a ? a->fault : HBNATIVE_FAULT_ARGUMENT;
}
unsigned HOT hbnative_pending_words(const hbnative *a) {
    return a ? a->fill : 0;
}

static bool HOT hbnative_healthy(void *ctx) {
    const hbnative *a = ctx;
    return a && !a->fault;
}
static bool HOT hbnative_available(void *ctx, unsigned bank) {
    hbnative *a = ctx;
    if (!a || a->fault) return false;
    if (bank >= S3_CAPTURE_BANKS) return hbnative_fail(a, HBNATIVE_FAULT_ARGUMENT);
    return !a->banks[bank].owned;
}
static bool HOT hbnative_reclaim(void *ctx, unsigned bank) {
    hbnative *a = ctx;
    if (!a || a->fault) return false;
    if (bank >= S3_CAPTURE_BANKS) return hbnative_fail(a, HBNATIVE_FAULT_ARGUMENT);
    return !a->banks[bank].owned || hbnative_fail(a, HBNATIVE_FAULT_RECLAIM);
}
static bool HOT AUDIT hbnative_accept(void *ctx, unsigned bank,
    const uint32_t *words, unsigned first, unsigned count, uint64_t sample,
    uint64_t now, uint64_t deadline) {
    hbnative *a = ctx;
    if (!a || a->fault) return false;
    if (bank >= S3_CAPTURE_BANKS || !words || ((uintptr_t)words & 3u) ||
        first >= S3_CAPTURE_WORDS || !count || count > S3_CAPTURE_WORDS)
        return hbnative_fail(a, HBNATIVE_FAULT_ARGUMENT);
    if (sample > UINT64_MAX - count)
        return hbnative_fail(a, HBNATIVE_FAULT_OVERFLOW);
    if (a->banks[bank].owned || a->count == S3_CAPTURE_BANKS)
        return hbnative_fail(a, HBNATIVE_FAULT_RECLAIM);
    if (sample != a->next_sample)
        return hbnative_fail(a, HBNATIVE_FAULT_SEQUENCE);
    if (now == UINT64_MAX || now < a->last_time)
        return hbnative_fail(a, HBNATIVE_FAULT_CLOCK);
    if (deadline <= now) return hbnative_fail(a, HBNATIVE_FAULT_DEADLINE);
    a->banks[bank] = (hbnative_bank){words, deadline, sample, first, count, 0, true};
    unsigned tail = a->head + a->count;
    if (tail >= S3_CAPTURE_BANKS) tail -= S3_CAPTURE_BANKS;
    a->fifo[tail] = bank;
    ++a->count;
    a->next_sample += count;
    a->last_time = now;
    return true;
}

s3_native_sink hbnative_sink(hbnative *a) {
    return (s3_native_sink){a, hbnative_healthy, hbnative_available,
                           hbnative_reclaim, hbnative_accept};
}

/* No arithmetic/packing here: every input bit, including metadata, survives.
 * Keep a named unit and explicit unroll so target copying is separately priced.
 */
static void HOT __attribute__((noinline, optimize("no-tree-loop-distribute-patterns")))
hbnative_copy_words(uint32_t *restrict dst,
    const uint32_t *restrict src, unsigned count) {
    while (count >= 8) {
        dst[0] = src[0]; dst[1] = src[1]; dst[2] = src[2]; dst[3] = src[3];
        dst[4] = src[4]; dst[5] = src[5]; dst[6] = src[6]; dst[7] = src[7];
        dst += 8; src += 8; count -= 8;
    }
    /* The per-function GCC option keeps 1..7 words as an auditable scalar
     * loop instead of an unpriced libc memcpy. No CPU barrier is added. */
    while (count--) *dst++ = *src++;
}

static void HOT AUDIT hbnative_advance(hbnative *a, unsigned taken) {
    hbnative_bank *b = &a->banks[a->fifo[a->head]];
    b->consumed += taken;
    a->consumed_samples += taken;
    if (b->consumed == b->count) {
        /* Source lease ends here, after copy or synchronous producer return.
         * Worker reads its workspace/carry-derived history, never this bank. */
        b->owned = false;
        if (++a->head == S3_CAPTURE_BANKS) a->head = 0;
        --a->count;
    }
}

static int HOT AUDIT hbnative_publish(hbnative *a, const uint32_t *raw,
    int16_t *output, hbnative_result *result) {
    if (!output) return HBNATIVE_NEED_OUTPUT;
    uint32_t sequence = a->pipe->produce_next;
    int rc = hbpipe_produce(a->pipe, raw, output);
    if (rc == HBPIPE_BUSY) return HBNATIVE_BUSY;
    if (rc != HBPIPE_OK) {
        hbnative_fail(a, HBNATIVE_FAULT_PIPE);
        return HBNATIVE_FAILED;
    }
    result->produced = 1;
    result->sequence = sequence;
    result->first_sample = a->produced_samples;
    a->produced_samples += HBPIPE_RAW;
    return HBNATIVE_OK;
}

static int HOT AUDIT hbnative_step(hbnative *a, int16_t *output,
    unsigned budget, hbnative_result *result) {
    if (!a->fill && a->count && budget == HBPIPE_RAW) {
        hbnative_bank *b = &a->banks[a->fifo[a->head]];
        unsigned at = (b->first + b->consumed) & (S3_CAPTURE_WORDS - 1u);
        if (b->count - b->consumed >= HBPIPE_RAW &&
            S3_CAPTURE_WORDS - at >= HBPIPE_RAW) {
            int rc = hbnative_publish(a, b->words + at, output, result);
            if (result->produced) {
                hbnative_advance(a, HBPIPE_RAW);
                result->consumed = HBPIPE_RAW;
            }
            return rc;
        }
    }
    /* At most three queued banks, at most two physical segments each, and
     * at most 1024 input words. No unbounded owner loop or zero-length copy. */
    while (a->count && budget && a->fill < HBPIPE_RAW) {
        hbnative_bank *b = &a->banks[a->fifo[a->head]];
        unsigned at = (b->first + b->consumed) & (S3_CAPTURE_WORDS - 1u);
        unsigned n = b->count - b->consumed;
        if (n > S3_CAPTURE_WORDS - at) n = S3_CAPTURE_WORDS - at;
        if (n > HBPIPE_RAW - a->fill) n = HBPIPE_RAW - a->fill;
        if (n > budget) n = budget;
        hbnative_copy_words(a->carry + a->fill, b->words + at, n);
        a->fill += n;
        budget -= n;
        result->consumed += n;
        result->copied += n;
        hbnative_advance(a, n);
    }
    if (a->fill == HBPIPE_RAW) {
        int rc = hbnative_publish(a, a->carry, output, result);
        if (result->produced) a->fill = 0;
        return rc;
    }
    return result->consumed ? HBNATIVE_OK : HBNATIVE_EMPTY;
}

static bool HOT AUDIT hbnative_read_clock(hbnative *a, s3_native_clock clock,
    void *ctx, uint32_t error, uint64_t *now) {
    uint64_t t = clock(ctx);
    if (t == UINT64_MAX || t < error || t < a->last_time)
        return hbnative_fail(a, HBNATIVE_FAULT_CLOCK);
    a->last_time = *now = t;
    return true;
}

int HOT AUDIT hbnative_step_clocked(hbnative *a, int16_t *output,
    unsigned max_words, s3_native_clock clock, void *ctx,
    uint32_t error, uint32_t bound, hbnative_result *result) {
    if (result) *result = (hbnative_result){0};
    if (!a || ((uintptr_t)a & 15u)) return HBNATIVE_INVALID;
    if (a->fault) return HBNATIVE_FAILED;
    if (!a->pipe || !result || !clock || max_words > HBPIPE_RAW ||
        !bound || error >= bound || (output && ((uintptr_t)output & 15u))) {
        hbnative_fail(a, HBNATIVE_FAULT_ARGUMENT);
        return HBNATIVE_INVALID;
    }
    uint64_t now;
    if (!hbnative_read_clock(a, clock, ctx, error, &now)) return HBNATIVE_FAILED;
    uint64_t earliest = UINT64_MAX;
    /* Check every retained source, including a backpressured bank that this
     * slice will not read. Strict inequality matches native capture leases. */
    for (unsigned n = 0; n < S3_CAPTURE_BANKS; ++n) {
        const hbnative_bank *b = &a->banks[n];
        if (!b->owned) continue;
        if (now >= b->deadline || bound >= b->deadline - now) {
            hbnative_fail(a, HBNATIVE_FAULT_DEADLINE);
            return HBNATIVE_FAILED;
        }
        if (b->deadline < earliest) earliest = b->deadline;
    }
    int rc = hbnative_step(a, output, max_words, result);
    uint64_t finished;
    if (!hbnative_read_clock(a, clock, ctx, error, &finished))
        return HBNATIVE_FAILED;
    if (finished - now > bound - error) {
        hbnative_fail(a, HBNATIVE_FAULT_BOUND);
        return HBNATIVE_FAILED;
    }
    if (finished >= earliest) {
        hbnative_fail(a, HBNATIVE_FAULT_DEADLINE);
        return HBNATIVE_FAILED;
    }
    return rc;
}

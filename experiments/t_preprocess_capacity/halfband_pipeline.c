#include "halfband_pipeline.h"
#include <limits.h>
#include <string.h>

_Static_assert(ATOMIC_INT_LOCK_FREE == 2, "slot publication must be lock-free");
_Static_assert(HBPIPE_CORE0_OUTPUT % 4 == 0, "whole SIMD output groups");
_Static_assert(HBPIPE_CORE0_OUTPUT < HBPIPE_OUTPUT, "both cores do work");

static inline int16_t component10(uint32_t word) {
    return (int16_t)((int32_t)(word << 22) >> 22);
}

/* Named noinline boundaries make the compiled unit costs independently
 * auditable. They do not add another copy of the original hb31_process caller.
 */
static __attribute__((noinline)) void hbpipe_unpack(hb31_workspace *w,
                                                   const uint32_t *raw) {
    for (size_t k = 0; k < HBPIPE_RAW / 2; ++k) {
        uint32_t even = raw[2*k], odd = raw[2*k+1];
        w->even[2*(k+15)] = component10(even);
        w->even[2*(k+15)+1] = component10(even >> 10);
        w->odd[2*(k+8)] = component10(odd);
        w->odd[2*(k+8)+1] = component10(odd >> 10);
    }
    w->even[2*(HBPIPE_OUTPUT+15)] = 0;
    w->even[2*(HBPIPE_OUTPUT+15)+1] = 0;
}

static __attribute__((noinline)) void hbpipe_prefix(hb31_workspace *w,
                                                    int16_t *out, uint32_t shift) {
    for (size_t k = 0; k < HBPIPE_CORE0_OUTPUT; k += 4)
        hb31_qacc4(w->even+2*k, w->odd+2*k, hb31_vectors, out+2*k, shift);
}

static __attribute__((noinline)) void hbpipe_suffix(hb31_workspace *w,
                                                    int16_t *out, uint32_t shift) {
    for (size_t k = HBPIPE_CORE0_OUTPUT; k < HBPIPE_OUTPUT; k += 4)
        hb31_qacc4(w->even+2*k, w->odd+2*k, hb31_vectors, out+2*k, shift);
}

int hbpipe_init(hbpipe *p, uint32_t shift) {
    if (!p || ((uintptr_t)p & 15u) || shift > 31u) return HBPIPE_INVALID;
    memset(p, 0, sizeof(*p));
    for (unsigned i = 0; i < HBPIPE_SLOTS; ++i)
        atomic_init(&p->slots[i].status, HBPIPE_FREE);
    p->shift = shift;
    return HBPIPE_OK;
}

size_t hbpipe_size(void) { return sizeof(hbpipe); }

int hbpipe_produce(hbpipe *p, const uint32_t *raw, int16_t *output) {
    if (!p || !raw || !output || ((uintptr_t)p & 15u) ||
        ((uintptr_t)raw & 3u) || ((uintptr_t)output & 15u)) return HBPIPE_INVALID;
    hbpipe_slot *s = &p->slots[p->produce_next & 1u];
    if (atomic_load_explicit(&s->status, memory_order_acquire) != HBPIPE_FREE)
        return HBPIPE_BUSY;
    hb31_workspace *w = &s->workspace;
    hb31_copy_words(w->even, p->history.even, HB31_EVEN_HISTORY);
    hb31_copy_words(w->odd, p->history.odd, HB31_ODD_HISTORY);
    hbpipe_unpack(w, raw);
    /* The producer can advance to another slot before this slot is consumed:
     * the consumer uses only its private workspace, never p->history. */
    hb31_copy_words(p->history.even, w->even+2*HBPIPE_OUTPUT, HB31_EVEN_HISTORY);
    hb31_copy_words(p->history.odd, w->odd+2*HBPIPE_OUTPUT, HB31_ODD_HISTORY);
    hbpipe_prefix(w, output, p->shift);
    s->output = output;
    s->sequence = p->produce_next;
    atomic_store_explicit(&s->status, HBPIPE_READY, memory_order_release);
    ++p->produce_next;
    return HBPIPE_OK;
}

int hbpipe_work(hbpipe *p) {
    if (!p) return HBPIPE_INVALID;
    hbpipe_slot *s = &p->slots[p->consume_next & 1u];
    if (atomic_load_explicit(&s->status, memory_order_acquire) != HBPIPE_READY)
        return HBPIPE_EMPTY;
    if (s->sequence != p->consume_next) return HBPIPE_ORDER;
    hbpipe_suffix(&s->workspace, s->output, p->shift);
    atomic_store_explicit(&s->status, HBPIPE_DONE, memory_order_release);
    ++p->consume_next;
    return HBPIPE_OK;
}

int hbpipe_reap(hbpipe *p, int16_t **output, uint32_t *sequence) {
    if (!p || !output || !sequence) return HBPIPE_INVALID;
    hbpipe_slot *s = &p->slots[p->reap_next & 1u];
    if (atomic_load_explicit(&s->status, memory_order_acquire) != HBPIPE_DONE)
        return HBPIPE_EMPTY;
    if (s->sequence != p->reap_next) return HBPIPE_ORDER;
    *output = s->output;
    *sequence = s->sequence;
    s->output = NULL;
    atomic_store_explicit(&s->status, HBPIPE_FREE, memory_order_release);
    ++p->reap_next;
    return HBPIPE_OK;
}

unsigned hbpipe_status(const hbpipe *p, unsigned slot) {
    if (!p || slot >= HBPIPE_SLOTS) return UINT_MAX;
    return atomic_load_explicit(&p->slots[slot].status, memory_order_acquire);
}

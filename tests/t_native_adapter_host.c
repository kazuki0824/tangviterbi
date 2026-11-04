#include "native_adapter.h"
#include <stddef.h>
#include <string.h>

static uint64_t clock_values[2];
static unsigned clock_calls;
static uint64_t host_clock(void *ctx) {
    (void)ctx;
    unsigned n = clock_calls++;
    return clock_values[n < 2 ? n : 1];
}
int host_step(hbnative *a, int16_t *out, unsigned words,
              uint64_t before, uint64_t after, unsigned error, unsigned bound,
              hbnative_result *result) {
    clock_values[0] = before; clock_values[1] = after; clock_calls = 0;
    return hbnative_step_clocked(a, out, words, host_clock, NULL, error, bound, result);
}
int host_accept(hbnative *a, unsigned bank, const uint32_t *words,
                unsigned first, unsigned count, uint64_t sample,
                uint64_t now, uint64_t deadline) {
    s3_native_sink sink = hbnative_sink(a);
    return sink.accept(sink.ctx, bank, words, first, count, sample, now, deadline);
}
int host_available(hbnative *a, unsigned bank) {
    s3_native_sink sink = hbnative_sink(a);
    return sink.available(sink.ctx, bank);
}
int host_reclaim(hbnative *a, unsigned bank) {
    s3_native_sink sink = hbnative_sink(a);
    return sink.reclaim(sink.ctx, bank);
}
uint64_t host_value(hbnative *a, unsigned field) {
    switch (field) {
    case 0: return a->count;
    case 1: return a->fill;
    case 2: return a->next_sample;
    case 3: return a->consumed_samples;
    case 4: return a->produced_samples;
    case 5: return a->last_time;
    case 6: return a->fault;
    default: return UINT64_MAX;
    }
}
uint32_t host_carry(hbnative *a, unsigned index) {
    return index < HBPIPE_RAW ? a->carry[index] : 0;
}
unsigned host_layout(unsigned item) {
    switch (item) {
    case 0: return sizeof(hbnative);
    case 1: return _Alignof(hbnative);
    case 2: return sizeof(hbnative_bank);
    case 3: return sizeof(hbnative_result);
    case 4: return offsetof(hbnative, carry);
    case 5: return sizeof(((hbnative *)0)->carry);
    default: return 0;
    }
}

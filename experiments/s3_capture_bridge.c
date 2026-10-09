#include "s3_capture_bridge.h"
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#define HOT IRAM_ATTR
#else
#define HOT
#endif
void s3_capture_init(s3_capture_bridge *b, s3_tx_ring *ring)
{
    memset(b, 0, sizeof(*b));
    s3_iq10_init(&b->packer, ring);
}
static bool HOT fail(s3_capture_bridge *b, enum s3_capture_fault code)
{
    if (!b->fault) b->fault = code;
    return false;
}
bool HOT s3_capture_accept(s3_capture_bridge *b, unsigned bank, const uint32_t *words,
                          unsigned first, unsigned count, uint64_t sample,
                          uint64_t now, uint64_t deadline)
{
    if (!b || b->fault) return false;
    if (bank >= S3_CAPTURE_BANKS || !words || first >= S3_CAPTURE_WORDS ||
        !count || count > S3_CAPTURE_WORDS || sample > UINT64_MAX-count)
        return fail(b,S3_CAPTURE_ARGUMENT);
    if (b->banks[bank].owned || b->count == S3_CAPTURE_BANKS)
        return fail(b,S3_CAPTURE_RECLAIM);
    if (sample != b->next_sample) return fail(b,S3_CAPTURE_SEQUENCE);
    if (deadline <= now) return fail(b,S3_CAPTURE_DEADLINE);
    b->banks[bank] = (s3_capture_bank){words, deadline, first, count, 0, true};
    b->fifo[(b->head+b->count)%S3_CAPTURE_BANKS] = bank;
    ++b->count; b->next_sample += count;
    return true;
}
bool HOT s3_capture_reclaim(s3_capture_bridge *b, unsigned bank)
{
    if (!b || b->fault) return false;
    if (bank >= S3_CAPTURE_BANKS) return fail(b,S3_CAPTURE_ARGUMENT);
    return !b->banks[bank].owned || fail(b,S3_CAPTURE_RECLAIM);
}
bool HOT s3_capture_step(s3_capture_bridge *b, unsigned max_words, uint64_t now,
                        uint32_t slice_bound, unsigned *consumed)
{
    if (!b || !consumed || b->fault) return false;
    *consumed = 0;
    if (!max_words || !slice_bound) return fail(b,S3_CAPTURE_ARGUMENT);
    /* All leases must survive the entire nonpreemptive slice. */
    for (unsigned i=0;i<S3_CAPTURE_BANKS;++i)
        if (b->banks[i].owned && (now >= b->banks[i].deadline ||
            slice_bound >= b->banks[i].deadline-now)) return fail(b,S3_CAPTURE_DEADLINE);
    if (!b->count) return true;
    s3_capture_bank *bank=&b->banks[b->fifo[b->head]];
    unsigned at=(bank->first+bank->consumed)%S3_CAPTURE_WORDS;
    unsigned n=bank->count-bank->consumed;
    if (n>max_words) n=max_words;
    if (n>S3_CAPTURE_WORDS-at) n=S3_CAPTURE_WORDS-at;
    size_t taken=0;
    int rc=s3_iq10_push(&b->packer,bank->words+at,n,&taken);
    if (rc!=S3_OK && rc!=S3_BUSY) return fail(b,S3_CAPTURE_ARGUMENT);
    bank->consumed+=(unsigned)taken; b->consumed_samples+=taken;
    *consumed=(unsigned)taken;
    if (bank->consumed==bank->count) {
        bank->owned=false; b->head=(b->head+1)%S3_CAPTURE_BANKS; --b->count;
    }
    return true;
}

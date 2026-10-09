#include "s3_transport.h"
#include <limits.h>

_Static_assert(ATOMIC_INT_LOCK_FREE == 2, "32-bit state must be lock-free");
_Static_assert(sizeof(unsigned) == 4, "32-bit state required");
enum { FREE, FILLING, READY, INFLIGHT, DONE };

static bool stream_valid(unsigned stream)
{
    return stream == S3_RF || stream == S3_FFT || stream == S3_IQ;
}

int s3_wire_make(s3_wire_header *out, unsigned stream, unsigned epoch,
                 uint32_t offset, size_t bytes)
{
    if (!out || !stream_valid(stream) || epoch == 0 || epoch > UINT16_MAX ||
        bytes != S3_PAGE_BYTES || offset % S3_PAGE_BYTES) return S3_RANGE;
    out->command = (uint16_t)(0xd710 | stream);
    out->address = ((uint64_t)epoch << 48) | ((uint64_t)offset << 16) | bytes;
    return S3_OK;
}

int s3_wire_read(s3_wire_header h, unsigned *stream, unsigned *epoch,
                 uint32_t *offset, size_t *bytes)
{
    if (!stream || !epoch || !offset || !bytes || (h.command & 0xfff0) != 0xd710)
        return S3_RANGE;
    unsigned s = h.command & 15, e = (unsigned)(h.address >> 48);
    uint32_t off = (uint32_t)(h.address >> 16);
    size_t n = h.address & 0xffff;
    s3_wire_header check;
    if (s3_wire_make(&check, s, e, off, n) != S3_OK) return S3_RANGE;
    *stream = s; *epoch = e; *offset = off; *bytes = n;
    return S3_OK;
}

void s3_wire_bytes(s3_wire_header h, uint8_t out[10])
{
    out[0] = (uint8_t)(h.command >> 8); out[1] = (uint8_t)h.command;
    for (unsigned i = 0; i < 8; ++i) out[2+i] = (uint8_t)(h.address >> (56-8*i));
}

static s3_ring_page *page(s3_tx_ring *r, uint32_t sequence)
{
    return &r->pages[sequence & (S3_RING_PAGES - 1)];
}

static bool matches(s3_tx_ring *r, s3_lease lease, unsigned state)
{
    s3_ring_page *p = page(r, lease.sequence);
    return lease.epoch == r->epoch &&
           atomic_load_explicit(&p->state, memory_order_acquire) == state &&
           p->sequence == lease.sequence;
}

int s3_ring_init(s3_tx_ring *r, void *payload, size_t size, unsigned epoch)
{
    if (!r || !payload || ((uintptr_t)payload & 3) || size != S3_RING_BYTES ||
        !epoch || epoch > UINT16_MAX) return S3_RANGE;
    r->payload = payload;
    r->write_sequence = r->submit_sequence = r->retire_sequence = 0;
    r->epoch = (uint16_t)epoch;
    for (unsigned i = 0; i < S3_RING_PAGES; ++i) {
        atomic_init(&r->pages[i].state, FREE); r->pages[i].sequence = 0;
    }
    return S3_OK;
}

int s3_ring_begin(s3_tx_ring *r, s3_lease *lease, uint8_t **payload)
{
    if (!r || !lease || !payload) return S3_RANGE;
    s3_ring_page *p = page(r, r->write_sequence);
    unsigned expected = FREE;
    if (!atomic_compare_exchange_strong_explicit(&p->state, &expected, FILLING,
            memory_order_acquire, memory_order_relaxed)) return S3_BUSY;
    p->sequence = r->write_sequence;
    *lease = (s3_lease){p->sequence, r->epoch};
    *payload = r->payload + (p->sequence & (S3_RING_PAGES - 1)) * S3_PAGE_BYTES;
    return S3_OK;
}

int s3_ring_publish(s3_tx_ring *r, s3_lease lease)
{
    if (!r || lease.sequence != r->write_sequence || !matches(r, lease, FILLING))
        return S3_STALE;
    atomic_store_explicit(&page(r, lease.sequence)->state, READY, memory_order_release);
    ++r->write_sequence;
    return S3_OK;
}

int s3_ring_take(s3_tx_ring *r, s3_lease *lease, const uint8_t **payload)
{
    if (!r || !lease || !payload) return S3_RANGE;
    s3_ring_page *p = page(r, r->submit_sequence);
    if (atomic_load_explicit(&p->state, memory_order_acquire) != READY ||
        p->sequence != r->submit_sequence) return S3_EMPTY;
    *lease = (s3_lease){p->sequence, r->epoch};
    *payload = r->payload + (p->sequence & (S3_RING_PAGES - 1)) * S3_PAGE_BYTES;
    atomic_store_explicit(&p->state, INFLIGHT, memory_order_relaxed);
    ++r->submit_sequence;
    return S3_OK;
}

int s3_ring_undo_take(s3_tx_ring *r, s3_lease lease)
{
    if (!r || r->submit_sequence != lease.sequence + 1 || !matches(r, lease, INFLIGHT))
        return S3_STALE;
    --r->submit_sequence;
    atomic_store_explicit(&page(r, lease.sequence)->state, READY, memory_order_release);
    return S3_OK;
}

int s3_ring_complete(s3_tx_ring *r, s3_lease lease)
{
    if (!r || !matches(r, lease, INFLIGHT)) return S3_STALE;
    atomic_store_explicit(&page(r, lease.sequence)->state, DONE, memory_order_relaxed);
    for (;;) {
        s3_ring_page *p = page(r, r->retire_sequence);
        if (atomic_load_explicit(&p->state, memory_order_relaxed) != DONE ||
            p->sequence != r->retire_sequence) break;
        atomic_store_explicit(&p->state, FREE, memory_order_release);
        ++r->retire_sequence;
    }
    return S3_OK;
}

int s3_ring_reset(s3_tx_ring *r)
{
    if (!r) return S3_RANGE;
    if (r->epoch == UINT16_MAX) return S3_EXHAUSTED;
    for (unsigned i = 0; i < S3_RING_PAGES; ++i) {
        unsigned s = atomic_load_explicit(&r->pages[i].state, memory_order_acquire);
        if (s == FILLING || s == INFLIGHT) return S3_BUSY;
    }
    return s3_ring_init(r, r->payload, S3_RING_BYTES, r->epoch + 1);
}

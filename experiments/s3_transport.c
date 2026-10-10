#include "s3_transport.h"
#include <limits.h>
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#define S3_HOT IRAM_ATTR
#else
#define S3_HOT
#endif

_Static_assert(sizeof(unsigned) == 4, "32-bit state required");
_Static_assert(S3_RING_PAGES && !(S3_RING_PAGES&(S3_RING_PAGES-1)), "power-of-two ring");
enum { FREE, FILLING, READY, INFLIGHT, DONE };

static S3_HOT bool stream_valid(unsigned stream)
{
    return stream == S3_RF || stream == S3_FFT || stream == S3_IQ;
}

int S3_HOT s3_wire_make(s3_wire_header *out, unsigned stream, unsigned epoch,
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

static S3_HOT s3_ring_page *page(s3_tx_ring *r, uint32_t sequence)
{
    return &r->pages[sequence & (S3_RING_PAGES - 1)];
}

static S3_HOT bool matches(s3_tx_ring *r, s3_lease lease, unsigned state)
{
    s3_ring_page *p = page(r, lease.sequence);
    return lease.epoch == r->epoch &&
           atomic_load_explicit(&p->state, memory_order_acquire) == state &&
           p->sequence == lease.sequence;
}

static S3_HOT uint8_t *page_payload(s3_tx_ring *r, uint32_t sequence)
{
    unsigned i=sequence&(S3_RING_PAGES-1);
    return i<r->head_pages ? r->payload+i*S3_PAGE_BYTES :
           r->payload_tail+(i-r->head_pages)*S3_PAGE_BYTES;
}

int s3_ring_init_split(s3_tx_ring *r, void *payload, unsigned head_pages,
                        void *tail, unsigned tail_pages, unsigned epoch)
{
    if (!r || !payload || ((uintptr_t)payload & 3) || !head_pages ||
        head_pages>S3_RING_PAGES || tail_pages!=S3_RING_PAGES-head_pages ||
        (tail_pages && (!tail || ((uintptr_t)tail&3))) ||
        !epoch || epoch > UINT16_MAX) return S3_RANGE;
    uintptr_t a=(uintptr_t)payload,b=(uintptr_t)tail;
    size_t na=head_pages*S3_PAGE_BYTES,nb=tail_pages*S3_PAGE_BYTES;
    if (a>UINTPTR_MAX-na || (tail_pages && (b>UINTPTR_MAX-nb ||
        (a<b+nb && b<a+na)))) return S3_RANGE;
    r->payload = payload;
    r->payload_tail=tail;r->head_pages=head_pages;
    r->write_sequence = r->submit_sequence = r->retire_sequence = 0;
    r->epoch = (uint16_t)epoch;
    for (unsigned i = 0; i < S3_RING_PAGES; ++i) {
        atomic_init(&r->pages[i].state, FREE); r->pages[i].sequence = 0;
    }
    return S3_OK;
}

int s3_ring_init(s3_tx_ring *r, void *payload, size_t size, unsigned epoch)
{
    if (size!=S3_RING_BYTES) return S3_RANGE;
    return s3_ring_init_split(r,payload,S3_RING_PAGES,NULL,0,epoch);
}

int S3_HOT s3_ring_begin(s3_tx_ring *r, s3_lease *lease, uint8_t **payload)
{
    if (!r || !lease || !payload) return S3_RANGE;
    s3_ring_page *p = page(r, r->write_sequence);
    if (atomic_load_explicit(&p->state, memory_order_acquire) != FREE) return S3_BUSY;
    /* Only this producer can claim FREE. The consumer only releases DONE;
     * a CAS is unnecessary, including on Xtensa's conditional-lock-free ABI. */
    atomic_store_explicit(&p->state, FILLING, memory_order_relaxed);
    p->sequence = r->write_sequence;
    *lease = (s3_lease){p->sequence, r->epoch};
    *payload = page_payload(r,p->sequence);
    return S3_OK;
}

int S3_HOT s3_ring_publish(s3_tx_ring *r, s3_lease lease)
{
    if (!r || lease.sequence != r->write_sequence || !matches(r, lease, FILLING))
        return S3_STALE;
    atomic_store_explicit(&page(r, lease.sequence)->state, READY, memory_order_release);
    ++r->write_sequence;
    return S3_OK;
}

int s3_ring_cancel_write(s3_tx_ring *r, s3_lease lease)
{
    if (!r || lease.sequence != r->write_sequence || !matches(r, lease, FILLING)) return S3_STALE;
    atomic_store_explicit(&page(r, lease.sequence)->state, FREE, memory_order_release);
    return S3_OK;
}

int S3_HOT s3_ring_take(s3_tx_ring *r, s3_lease *lease, const uint8_t **payload)
{
    if (!r || !lease || !payload) return S3_RANGE;
    s3_ring_page *p = page(r, r->submit_sequence);
    if (atomic_load_explicit(&p->state, memory_order_acquire) != READY ||
        p->sequence != r->submit_sequence) return S3_EMPTY;
    *lease = (s3_lease){p->sequence, r->epoch};
    *payload = page_payload(r,p->sequence);
    atomic_store_explicit(&p->state, INFLIGHT, memory_order_relaxed);
    ++r->submit_sequence;
    return S3_OK;
}

int S3_HOT s3_ring_undo_take(s3_tx_ring *r, s3_lease lease)
{
    if (!r || r->submit_sequence != lease.sequence + 1 || !matches(r, lease, INFLIGHT))
        return S3_STALE;
    --r->submit_sequence;
    atomic_store_explicit(&page(r, lease.sequence)->state, READY, memory_order_release);
    return S3_OK;
}

int S3_HOT s3_ring_complete(s3_tx_ring *r, s3_lease lease)
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
    return s3_ring_init_split(r,r->payload,r->head_pages,r->payload_tail,
                              S3_RING_PAGES-r->head_pages,r->epoch+1);
}

void s3_iq10_init(s3_iq10_packer *p, s3_tx_ring *r)
{
    memset(p, 0, sizeof(*p)); p->ring = r;
}

static S3_HOT void pack_eight(uint8_t *dst, const uint32_t *src)
{
    const uint32_t a=src[0]&0xfffffu, b=src[1]&0xfffffu, c=src[2]&0xfffffu, d=src[3]&0xfffffu;
    const uint32_t e=src[4]&0xfffffu, f=src[5]&0xfffffu, g=src[6]&0xfffffu, h=src[7]&0xfffffu;
    const uint32_t w[5]={a|(b<<20), (b>>12)|(c<<8)|(d<<28), (d>>4)|(e<<16),
                          (e>>16)|(f<<4)|(g<<24), (g>>8)|(h<<12)};
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    memcpy(dst,w,sizeof(w));
#else
    for (unsigned i=0;i<20;++i) dst[i]=(uint8_t)(w[i/4]>>(8*(i%4)));
#endif
}

int S3_HOT s3_iq10_push(s3_iq10_packer *p, const uint32_t *words, size_t count, size_t *consumed)
{
    if (!p || !p->ring || !consumed || (!words && count)) return S3_RANGE;
    *consumed=0;
    while (*consumed<count || p->pending_index<p->pending_size) {
        if (!p->page) {
            int err=s3_ring_begin(p->ring,&p->writing,&p->page);
            if (err!=S3_OK) return err;
            p->used=0;
        }
        if (p->pending_index<p->pending_size) {
            unsigned n=p->pending_size-p->pending_index;
            if (n>S3_PAGE_BYTES-p->used) n=S3_PAGE_BYTES-p->used;
            memcpy(p->page+p->used,p->pending+p->pending_index,n);
            p->used+=n; p->pending_index+=n;
        } else if (!p->have_first && !(p->used&3) && S3_PAGE_BYTES-p->used>=20 && count-*consumed>=8) {
            pack_eight(p->page+p->used,words+*consumed);
            p->used+=20; *consumed+=8;
        } else {
            if (!p->have_first) { p->first=words[(*consumed)++]&0xfffffu; p->have_first=true; }
            if (*consumed==count) break;
            uint32_t a=p->first,b=words[(*consumed)++]&0xfffffu;
            p->pending[0]=(uint8_t)a; p->pending[1]=(uint8_t)(a>>8);
            p->pending[2]=(uint8_t)((a>>16)|(b<<4));
            p->pending[3]=(uint8_t)(b>>4); p->pending[4]=(uint8_t)(b>>12);
            p->pending_index=0; p->pending_size=5; p->have_first=false;
        }
        if (p->used==S3_PAGE_BYTES) {
            int err=s3_ring_publish(p->ring,p->writing);
            if (err!=S3_OK) return err;
            p->page=NULL;
        }
    }
    return S3_OK;
}

int s3_iq10_discard(s3_iq10_packer *p)
{
    if (!p || !p->ring) return S3_RANGE;
    if (p->page) {
        int err=s3_ring_cancel_write(p->ring,p->writing);
        if (err!=S3_OK) return err;
    }
    s3_iq10_init(p,p->ring);
    return S3_OK;
}

unsigned S3_HOT s3_t_rf_batch(unsigned available, uint64_t now, uint64_t release,
                              uint64_t deadline, uint64_t full_ready, s3_batch_timing b)
{
    if (now >= release || deadline <= now || release > deadline) return 0;
    /* At 240 MHz CPU and 80 MHz Octal: (4096+10) bytes take 12318 cycles. */
    uint64_t segment = 12318u + (uint64_t)b.segment_cycles;
    uint64_t fft = b.API_cycles + 8u*segment;
    uint64_t remain = deadline - now;
    if (fft > remain || release-now > remain-fft) return 0;
    remain -= fft;
    if (available < 3 && full_ready < release) {
        uint64_t wait = full_ready > now ? full_ready-now : 0;
        uint64_t rf = b.API_cycles + 3u*segment;
        if (wait <= remain && rf <= remain-wait) return 0;
    }
    unsigned n = available > 3 ? 3 : available;
    while (n && b.API_cycles + n*segment > remain) --n;
    return n;
}

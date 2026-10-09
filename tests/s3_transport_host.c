#include "s3_transport.h"
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>

static _Alignas(16) uint8_t data[S3_RING_BYTES];
static s3_tx_ring ring;
enum { TEST_PAGES = 10000 };

static uint8_t pattern(uint32_t seq, unsigned i) { return (uint8_t)(seq*17u + i*29u + (i>>8)); }
static void *produce(void *unused)
{
    (void)unused;
    for (uint32_t seq = 0; seq < TEST_PAGES; ++seq) {
        s3_lease l; uint8_t *p;
        while (s3_ring_begin(&ring, &l, &p) == S3_BUSY) sched_yield();
        assert(l.sequence == seq);
        for (unsigned i = 0; i < S3_PAGE_BYTES; ++i) p[i] = pattern(seq,i);
        assert(s3_ring_publish(&ring, l) == S3_OK);
    }
    return NULL;
}

static void check_payload(const uint8_t *p, uint32_t seq)
{
    assert(p >= data && p + S3_PAGE_BYTES <= data + sizeof(data));
    for (unsigned i = 0; i < S3_PAGE_BYTES; ++i) assert(p[i] == pattern(seq,i));
}

static void *consume(void *unused)
{
    (void)unused;
    for (uint32_t seq = 0; seq < TEST_PAGES; seq += 2) {
        s3_lease l[2]; const uint8_t *p[2];
        for (unsigned j = 0; j < 2; ++j) {
            while (s3_ring_take(&ring, &l[j], &p[j]) == S3_EMPTY) sched_yield();
            assert(l[j].sequence == seq+j); check_payload(p[j], seq+j);
        }
        /* Simulate the faster second SPI port completing first. The first
         * buffer must remain unchanged until its own completion is reaped. */
        assert(s3_ring_complete(&ring,l[1]) == S3_OK);
        assert(s3_ring_complete(&ring,l[1]) == S3_STALE);
        check_payload(p[0],seq);
        assert(s3_ring_complete(&ring,l[0]) == S3_OK);
    }
    return NULL;
}

static void boundaries(void)
{
    assert(s3_ring_init(&ring,data,sizeof(data),1)==S3_OK);
    s3_lease l[8], out, stale; uint8_t *p; const uint8_t *q;
    assert(s3_ring_take(&ring,&out,&q)==S3_EMPTY);
    assert(s3_ring_begin(&ring,&stale,&p)==S3_OK);
    assert(s3_ring_reset(&ring)==S3_BUSY);
    assert(s3_ring_publish(&ring,stale)==S3_OK);
    for (unsigned i=1;i<8;++i) {
        assert(s3_ring_begin(&ring,&out,&p)==S3_OK);
        assert(s3_ring_publish(&ring,out)==S3_OK);
    }
    assert(s3_ring_begin(&ring,&out,&p)==S3_BUSY);
    for (unsigned i=0;i<8;++i) assert(s3_ring_take(&ring,&l[i],&q)==S3_OK);
    assert(s3_ring_reset(&ring)==S3_BUSY);
    assert(s3_ring_undo_take(&ring,l[0])==S3_STALE);
    assert(s3_ring_undo_take(&ring,l[7])==S3_OK);
    assert(s3_ring_take(&ring,&l[7],&q)==S3_OK);
    for (unsigned i=7;i>0;--i) assert(s3_ring_complete(&ring,l[i])==S3_OK);
    assert(s3_ring_begin(&ring,&out,&p)==S3_BUSY); // no prefix retired
    assert(s3_ring_complete(&ring,l[0])==S3_OK);
    assert(s3_ring_reset(&ring)==S3_OK);
    assert(ring.epoch==2);
    assert(s3_ring_complete(&ring,stale)==S3_STALE);
    assert(s3_ring_publish(&ring,stale)==S3_STALE);
    /* Unsent old-mode data may be explicitly discarded after RF stop. */
    assert(s3_ring_begin(&ring,&out,&p)==S3_OK);
    assert(s3_ring_publish(&ring,out)==S3_OK);
    assert(s3_ring_reset(&ring)==S3_OK);
    assert(s3_ring_take(&ring,&out,&q)==S3_EMPTY);
    /* Counter arithmetic crosses UINT32_MAX without signed overflow. */
    ring.write_sequence=ring.submit_sequence=ring.retire_sequence=UINT32_MAX-3;
    for (unsigned i=0;i<12;++i) {
        assert(s3_ring_begin(&ring,&out,&p)==S3_OK);
        assert(s3_ring_publish(&ring,out)==S3_OK);
        assert(s3_ring_take(&ring,&out,&q)==S3_OK);
        assert(s3_ring_complete(&ring,out)==S3_OK);
    }
    assert(ring.write_sequence==8 && ring.retire_sequence==8);
    ring.epoch=UINT16_MAX;
    assert(s3_ring_reset(&ring)==S3_EXHAUSTED);
    assert(s3_ring_init(&ring,data+1,sizeof(data),1)==S3_RANGE);
}

static void wire(void)
{
    s3_wire_header h; uint8_t bytes[10]; unsigned s,e; uint32_t offset; size_t length;
    assert(s3_wire_make(&h,S3_FFT,0x1234,0x56789000,4096)==S3_OK);
    s3_wire_bytes(h,bytes);
    const uint8_t golden[10]={0xd7,0x12,0x12,0x34,0x56,0x78,0x90,0x00,0x10,0x00};
    assert(memcmp(bytes,golden,sizeof(golden))==0);
    assert(s3_wire_read(h,&s,&e,&offset,&length)==S3_OK);
    assert(s==S3_FFT && e==0x1234 && offset==0x56789000 && length==4096);
    h.command^=0x100; assert(s3_wire_read(h,&s,&e,&offset,&length)==S3_RANGE);
    assert(s3_wire_make(&h,3,1,0,4096)==S3_RANGE);
    assert(s3_wire_make(&h,S3_RF,0,0,4096)==S3_RANGE);
    assert(s3_wire_make(&h,S3_RF,1,1,4096)==S3_RANGE);
    assert(s3_wire_make(&h,S3_IQ,1,0,4092)==S3_RANGE);
    assert(s3_wire_make(&h,S3_IQ,65535,0xfffff000,4096)==S3_OK);
    s3_wire_bytes(h,bytes); assert(bytes[1]==0x1b);
}

static void packed_adc_values(void)
{
    assert(s3_ring_init(&ring,data,sizeof(data),8)==S3_OK);
    s3_iq10_packer packer; s3_iq10_init(&packer,&ring);
    uint32_t source=0,decoded=0;
    uint64_t bits=0; unsigned bit_count=0,full_count=0;
    while (source < (1u<<20)) {
        uint32_t words[97];
        unsigned n=(source%97)+1;
        if (n>(1u<<20)-source) n=(1u<<20)-source;
        for (unsigned i=0;i<n;++i) words[i]=(source+i)|0xa5a00000u;
        size_t consumed=0;
        int err=s3_iq10_push(&packer,words,n,&consumed);
        assert(err==S3_OK || err==S3_BUSY); source+=(uint32_t)consumed;
        if (err==S3_BUSY || source==(1u<<20)) {
            full_count+=err==S3_BUSY;
            s3_lease l; const uint8_t *p;
            while (s3_ring_take(&ring,&l,&p)==S3_OK) {
                for (unsigned i=0;i<S3_PAGE_BYTES;++i) {
                    bits|=(uint64_t)p[i]<<bit_count; bit_count+=8;
                    if (bit_count>=20) {
                        assert((bits&0xfffffu)==decoded++); bits>>=20; bit_count-=20;
                    }
                }
                assert(s3_ring_complete(&ring,l)==S3_OK);
            }
        }
    }
    /* Flush saved bytes without inventing a final partial word or padding. */
    size_t consumed=123;
    assert(s3_iq10_push(&packer,NULL,0,&consumed)==S3_OK && consumed==0);
    assert(decoded==(1u<<20) && bit_count==0 && bits==0 && full_count>0);
    assert(packer.page==NULL && !packer.have_first);
    /* A partial native sample pair is discarded only on explicit mode stop. */
    const uint32_t one=0xabcde;
    assert(s3_iq10_push(&packer,&one,1,&consumed)==S3_OK && consumed==1);
    assert(s3_ring_reset(&ring)==S3_BUSY);
    assert(s3_iq10_discard(&packer)==S3_OK);
    assert(s3_ring_reset(&ring)==S3_OK);
}

int main(void)
{
    s3_batch_timing timing={4800,60}; // Conditional 20 us API / 0.25 us segment
    const uint64_t deadline=249480, release=120000, fft_cost=103824, rf3=41934;
    uint64_t last3=deadline-fft_cost-rf3;
    assert(s3_t_rf_batch(3,last3,release,deadline,0,timing)==3);
    assert(s3_t_rf_batch(3,last3+1,release,deadline,0,timing)==2);
    assert(s3_t_rf_batch(3,release,release,deadline,0,timing)==0);
    assert(s3_t_rf_batch(1,0,release,deadline,1000,timing)==0); // wait for batch
    assert(s3_t_rf_batch(1,100000,release,deadline,200000,timing)==1);
    assert(s3_t_rf_batch(3,UINT64_MAX-10,UINT64_MAX-5,UINT64_MAX,0,timing)==0);
    wire(); boundaries(); packed_adc_values();
    assert(s3_ring_init(&ring,data,sizeof(data),7)==S3_OK);
    pthread_t producer,consumer;
    assert(pthread_create(&producer,NULL,produce,NULL)==0);
    assert(pthread_create(&consumer,NULL,consume,NULL)==0);
    assert(pthread_join(producer,NULL)==0); assert(pthread_join(consumer,NULL)==0);
    assert(ring.retire_sequence==TEST_PAGES);
    printf("{\"pages\":%d,\"payload_bytes_checked\":%u,\"out_of_order_pairs\":%d,"
           "\"native_IQ10_values_checked\":1048576,\"wire_and_wrap_and_stop_boundaries\":true,\"all_pass\":true}\n",
           TEST_PAGES,TEST_PAGES*S3_PAGE_BYTES,TEST_PAGES/2);
    return 0;
}

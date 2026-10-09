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

int main(void)
{
    wire(); boundaries();
    assert(s3_ring_init(&ring,data,sizeof(data),7)==S3_OK);
    pthread_t producer,consumer;
    assert(pthread_create(&producer,NULL,produce,NULL)==0);
    assert(pthread_create(&consumer,NULL,consume,NULL)==0);
    assert(pthread_join(producer,NULL)==0); assert(pthread_join(consumer,NULL)==0);
    assert(ring.retire_sequence==TEST_PAGES);
    printf("{\"pages\":%d,\"payload_bytes_checked\":%u,\"out_of_order_pairs\":%d,"
           "\"wire_and_wrap_and_stop_boundaries\":true,\"all_pass\":true}\n",
           TEST_PAGES,TEST_PAGES*S3_PAGE_BYTES,TEST_PAGES/2);
    return 0;
}

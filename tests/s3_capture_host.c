#include "s3_capture_bridge.h"
#include <assert.h>
#include <stdio.h>
static _Alignas(16) unsigned char payload[S3_RING_BYTES];
static uint32_t raw[3][S3_CAPTURE_WORDS];
static s3_tx_ring ring;
static s3_capture_bridge bridge;
static uint64_t out_bytes;
static uint32_t word(uint64_t i) {return (uint32_t)(i*2311+17)&0xfffffu;}
static void drain(void)
{
    s3_lease lease; const uint8_t *p;
    while(s3_ring_take(&ring,&lease,&p)==S3_OK) {
        for(unsigned i=0;i<S3_PAGE_BYTES;++i) {
            uint64_t bit=(out_bytes+i)*8, sample=bit/20;
            unsigned shift=bit%20;
            uint64_t v=word(sample)|((uint64_t)word(sample+1)<<20);
            assert(p[i]==((v>>shift)&255));
        }
        out_bytes+=S3_PAGE_BYTES;
        assert(s3_ring_complete(&ring,lease)==S3_OK);
    }
}
int main(void)
{
    assert(s3_ring_init(&ring,payload,sizeof(payload),1)==S3_OK);
    s3_capture_init(&bridge,&ring);
    uint64_t sample=0,now=0;
    for(unsigned unit=0;unit<90;++unit) {
        unsigned bank=unit%3, first=(unit*1321+16000)%S3_CAPTURE_WORDS;
        unsigned n=12288+unit%2001;
        assert(s3_capture_reclaim(&bridge,bank));
        for(unsigned j=0;j<n;++j) raw[bank][(first+j)%S3_CAPTURE_WORDS]=word(sample+j)|0xabc00000u;
        assert(s3_capture_accept(&bridge,bank,raw[bank],first,n,sample,now,now+1000000));
        unsigned taken;
        while(bridge.count) {
            assert(s3_capture_step(&bridge,511,now++,2,&taken));
            if(!taken) drain();
        }
        drain(); sample+=n;
    }
    assert(bridge.consumed_samples==sample);
    assert(s3_capture_accept(&bridge,0,raw[0],0,12288,sample,now,now+1000));
    unsigned taken;
    assert(!s3_capture_step(&bridge,512,now+998,2,&taken));
    assert(bridge.fault==S3_CAPTURE_DEADLINE && bridge.banks[0].owned);
    s3_capture_init(&bridge,&ring);
    assert(s3_capture_accept(&bridge,0,raw[0],0,12288,0,0,100));
    assert(!s3_capture_reclaim(&bridge,0));
    assert(bridge.fault==S3_CAPTURE_RECLAIM);
    s3_capture_init(&bridge,&ring);
    assert(!s3_capture_accept(&bridge,0,raw[0],0,12288,1,0,100));
    assert(bridge.fault==S3_CAPTURE_SEQUENCE);
    printf("{\"units\":90,\"samples\":%llu,\"checked_bytes\":%llu,\"all_pass\":true}\n",
           (unsigned long long)sample,(unsigned long long)out_bytes);
}

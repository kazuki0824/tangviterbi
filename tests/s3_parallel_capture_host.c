#include "s3_parallel_capture.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
enum {CTRL=0x60033d5c,INDEX=0x60033d60,SELECT=0x600c101c};
static struct hw {uint32_t banks[3][16384];uint64_t cycles,samples;unsigned cpp,phase,index,mask;bool run;} h;
static void tick(unsigned cycles){
 h.cycles+=cycles;
 if(!h.run)return;
 h.phase+=cycles;
 while(h.phase>=h.cpp){h.phase-=h.cpp;for(unsigned b=0;b<3;b++)if(h.mask&(1u<<b))h.banks[b][h.index]=h.samples&0xfffff;
  h.samples++;h.index=(h.index+1)&16383;
 }
}
static uint32_t rd(void*c,uint32_t a){(void)c;if(a==INDEX){tick(h.cpp);return h.index;}if(a==SELECT)return h.mask;return 0;}
static void wr(void*c,uint32_t a,uint32_t v){(void)c;tick(h.cpp);if(a==CTRL)h.run=(v>>31)!=0;if(a==SELECT)h.mask=v&15;}
static uint32_t cycles(void*c){(void)c;return h.cycles;}
static uint32_t* bank(void*c,unsigned b){(void)c;return h.banks[b];}
static uint8_t expected(uint64_t at){uint64_t a=((at/5)*2)&0xfffff,b=(a+1)&0xfffff;return ((a|(b<<20))>>((at%5)*8))&255;}

static _Alignas(16) uint8_t payload[4][S3_PP_CHUNK];
static void consume(s3_parallel_pack*p,uint64_t*bytes) {
 uint64_t seq;const uint8_t*data;
 while(s3_pp_take(p,&seq,&data)==S3_PP_OK) {
  assert(seq*S3_PP_CHUNK==*bytes);
  for(unsigned i=0;i<S3_PP_CHUNK;++i)assert(data[i]==expected((*bytes)++));
  assert(s3_pp_complete(p,seq)==S3_PP_OK);
 }
}
int main(void) {
 for(unsigned rate=16;rate<=40;rate+=24)for(unsigned stall=0;stall<2;++stall) {
  memset(&h,0,sizeof(h));h.cpp=240/rate;h.cycles=UINT32_MAX-5000u;
  s3_parallel_pack p;s3_native_capture capture={0};
  uint8_t*buffers[4]={payload[0],payload[1],payload[2],payload[3]};
  assert(s3_pp_init(&p,buffers)==S3_PP_OK);
  s3_native_io io={rd,wr,cycles,bank,0};
  assert(s3_pp_native_start(&capture,&p,io,rate));uint64_t bytes=0;
  for(unsigned i=0;i<100000 && capture.running && capture.unit<80;++i) {
   tick(240);
   if(s3_pp_collect(&p,capture.now)!=S3_PP_OK){s3_native_stop(&capture);break;}
   if(!s3_native_poll(&capture))break;
   unsigned n;
   for(unsigned w=0;w<(stall?1u:2u);++w) {
    int rc=s3_pp_step(&p,w,128,capture.now,1000,&n);
    if(rc!=S3_PP_OK && rc!=S3_PP_EMPTY){s3_native_stop(&capture);break;}
   }
   consume(&p,&bytes);
  }
  if(stall) {
   assert(capture.fault || atomic_load(&p.fault));
   assert(!capture.running && !h.run && capture.unit<5);
  } else {
   assert(!capture.fault && capture.unit==80 && !atomic_load(&p.fault));
   s3_native_stop(&capture);
   while(p.count) {
    unsigned n;
    for(unsigned w=0;w<2;++w) {
     int rc=s3_pp_step(&p,w,8192,capture.now,1000,&n);
     assert(rc==S3_PP_OK || rc==S3_PP_EMPTY);
    }
    assert(s3_pp_collect(&p,capture.now)==S3_PP_OK);consume(&p,&bytes);
   }
   assert(bytes>2000000);
   assert(p.published==(p.next_sample/2)*5);
   assert(!s3_pp_native_start(&capture,&p,io,rate)); // stale stream cannot restart
  }
  printf("PASS native adapter rate=%u stalled_worker=%u banks=%u checked_bytes=%llu synthetic_poll_cycles=240 WCET_measured=false\n",
   rate,stall,capture.unit,(unsigned long long)bytes);
 }
 return 0;
}

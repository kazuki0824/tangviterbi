#include "s3_native_capture.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
enum {CTRL=0x60033d5c,INDEX=0x60033d60,SELECT=0x600c101c};
static struct hw {uint32_t banks[3][16384];uint64_t cycles,samples;unsigned cpp,phase,index,mask;bool run;} h;
static uint8_t queue[S3_RING_BYTES];
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
static unsigned consume(s3_tx_ring*r,uint64_t*bytes){
 s3_lease lease;const uint8_t*p;unsigned pages=0;
 while(s3_ring_take(r,&lease,&p)==S3_OK){for(unsigned i=0;i<4096;i++)assert(p[i]==expected((*bytes)++));assert(s3_ring_complete(r,lease)==S3_OK);pages++;}return pages;
}
int main(void){
 unsigned cases=0;uint64_t checked=0;
 for(unsigned rate=16;rate<=40;rate+=24)for(unsigned stall=0;stall<2;stall++){
  memset(&h,0,sizeof(h));h.cpp=240/rate;h.cycles=UINT32_MAX-5000u;
  s3_tx_ring ring;s3_capture_bridge bridge;s3_native_capture capture={0};
  assert(s3_ring_init(&ring,queue,sizeof(queue),1)==S3_OK);s3_capture_init(&bridge,&ring);
  s3_native_io io={rd,wr,cycles,bank,0};assert(s3_native_start(&capture,&bridge,io,rate));
  uint64_t bytes=0;
  for(unsigned i=0;i<100000 && capture.running && capture.unit<80;i++){
   tick(240);if(!s3_native_poll(&capture))break;
   if(!stall){unsigned taken;assert(s3_capture_step(&bridge,256,capture.now,1000,&taken));consume(&ring,&bytes);}
  }
  if(stall){assert(capture.fault);assert(!capture.running&&!h.run);assert(capture.unit<5);}
  else {assert(!capture.fault&&capture.unit==80);s3_native_stop(&capture);assert(!h.run);
   while(bridge.count){unsigned taken;assert(s3_capture_step(&bridge,256,capture.now,1000,&taken));consume(&ring,&bytes);}
   assert(bridge.next_sample==bridge.consumed_samples);assert(bytes>2000000);checked+=bytes;
  }
  ++cases;
 }
 printf("PASS native RF model cases=%u checked_payload_bytes=%llu\n",cases,(unsigned long long)checked);
}

#include "s3_native_capture.h"
#include "s3_fft_worker.h"
#include "s3_fft_capture_service.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
enum {CTRL=0x60033d5c,INDEX=0x60033d60,SELECT=0x600c101c};
static struct hw {uint32_t banks[3][16384];uint64_t cycles,samples;unsigned cpp,phase,index,mask;bool run;} h;
static uint8_t queue[S3_RING_BYTES];
static _Alignas(16) int16_t fft_frame[16384],fft_table[8192];
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
/* Synthetic 24-cycle tile for RF handoff integration, NOT a SIMD timing model.
 * Independent test_s3_fft_worker uses real ANSI tile arithmetic and all bins.
 */
int s3_fft_simd_tile_n(int16_t*d,const int16_t*t,unsigned points,unsigned s,unsigned b,unsigned n){
 (void)points;
 (void)d;(void)t;(void)s;(void)b;assert(n==16);tick(24);return 0;
}
struct pump_context {s3_tx_ring *ring;uint64_t *bytes;};
static bool pump(void*ctx){struct pump_context*p=ctx;consume(p->ring,p->bytes);return true;}
int main(void){
 unsigned cases=0,frames=0;uint64_t checked=0;
 for(unsigned rate=16;rate<=40;rate+=24)for(unsigned stall=0;stall<2;stall++){
  memset(&h,0,sizeof(h));h.cpp=240/rate;h.cycles=UINT32_MAX-5000u;
  s3_tx_ring ring;s3_capture_bridge bridge;s3_native_capture capture={0};
  assert(s3_ring_init(&ring,queue,sizeof(queue),1)==S3_OK);s3_capture_init(&bridge,&ring);
  s3_native_io io={rd,wr,cycles,bank,0};assert(s3_native_start(&capture,&bridge,io,rate));
  uint64_t bytes=0;
  struct pump_context pc={&ring,&bytes};
  s3_fft_capture_service service={&capture,stall?1u:256u,1000,pump,&pc};
  s3_fft_worker worker;
  assert(s3_fft_worker_init(&worker,fft_frame,fft_table,s3_fft_service_capture,&service,NULL,NULL));
  for(unsigned i=0;i<100000 && capture.running && capture.unit<80;i++){
   tick(240);
   int a=s3_fft_worker_step(&worker,0),b=s3_fft_worker_step(&worker,1);
   if(a<0||b<0){assert(!s3_fft_worker_ready(&worker));break;}
   if(s3_fft_worker_ready(&worker)){
    ++frames;
    assert(s3_fft_worker_init(&worker,fft_frame,fft_table,s3_fft_service_capture,&service,NULL,NULL));
   }
  }
  if(stall){assert(capture.fault||bridge.fault);assert(!capture.running&&!h.run);assert(capture.unit<5);}
  else {assert(!capture.fault&&capture.unit==80);s3_native_stop(&capture);assert(!h.run);
   while(bridge.count){unsigned taken;assert(s3_capture_step(&bridge,256,capture.now,1000,&taken));consume(&ring,&bytes);}
   assert(bridge.next_sample==bridge.consumed_samples);assert(bytes>2000000);checked+=bytes;
  }
  ++cases;
 }
 printf("PASS native RF + bounded worker model cases=%u FFT_frames=%u checked_payload_bytes=%llu synthetic_tile_cycles=24 SIMD_executed=false\n",cases,frames,(unsigned long long)checked);
}

/* Replay synthetic accept/publication/SPI ordering through the real packer.
 * No S3 elapsed time is measured; stop at the first expected capacity failure. */
#include "s3_parallel_pack.h"
#include <assert.h>
#include <stdio.h>
struct event { unsigned kind, bank, count, busy; unsigned long long seq, time; };
#include "events.h"
static _Alignas(16) uint8_t arena[4][S3_PP_CHUNK];
static uint32_t source[3][S3_PP_WORDS];
static s3_parallel_pack p;
static uint32_t value(uint64_t n) { return (uint32_t)(n*65497u+71u)&0xfffff; }
static uint8_t expected(uint64_t byte) {
 uint64_t pair=byte/5,bits=value(2*pair)|((uint64_t)value(2*pair+1)<<20);
 return (uint8_t)(bits>>(8*(byte%5)));
}
int main(void) {
 uint8_t*buffers[4]={arena[0],arena[1],arena[2],arena[3]};
 assert(s3_pp_init(&p,buffers)==S3_PP_OK);
 for(unsigned i=0;i<sizeof(events)/sizeof(events[0]);++i){
  const struct event*e=&events[i];
  if(e->kind==0){
   assert(s3_pp_reclaim(&p,e->bank)==S3_PP_OK);
   for(unsigned n=0;n<e->count;++n)source[e->bank][n]=value(e->seq+n);
   int rc=s3_pp_accept(&p,e->bank,source[e->bank],0,e->count,e->seq,e->time,UINT64_MAX);
   if(e->busy){assert(rc==S3_PP_BUSY&&!atomic_load(&p.fault));printf("PASS expected BUSY at %llu cycles\n",e->time);return 0;}
   assert(rc==S3_PP_OK);
  }else if(e->kind==1){
   for(unsigned w=0;w<2;++w){unsigned n;assert(s3_pp_step(&p,w,8192,e->time,1,&n)==S3_PP_OK);}
   assert(s3_pp_collect(&p,e->time)==S3_PP_OK);
  }else if(e->kind==2){assert(s3_pp_complete(&p,e->seq)==S3_PP_OK);
  }else{
   uint64_t seq;const uint8_t*data;assert(s3_pp_take(&p,&seq,&data)==S3_PP_OK&&seq==e->seq);
   for(unsigned n=0;n<S3_PP_TX_BYTES;++n)assert(data[n]==expected(seq*S3_PP_TX_BYTES+n));
  }
 }
 puts("PASS complete finite trace, exact payload and ordered leases");
}

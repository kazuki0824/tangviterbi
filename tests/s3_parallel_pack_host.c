#include "s3_parallel_pack.h"
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef S3_PP_CORE0_SIXTEENTHS
#define S3_PP_CORE0_SIXTEENTHS 8
#endif
static _Alignas(16) uint8_t data[4][S3_PP_CHUNK];
static uint32_t source[3][S3_PP_WORDS];
static s3_parallel_pack p;
static atomic_uint stop_flag;
static uint32_t sample(uint64_t n) {return (uint32_t)(n*65497u+(n>>11)*713u+71u)&0xfffff;}
static uint8_t byte(uint64_t n) {
 uint64_t pair=n/5,v=sample(pair*2)|((uint64_t)sample(pair*2+1)<<20);
 return (uint8_t)(v>>(8*(n%5)));
}
static void init(void) {
 uint8_t *buffers[4]={data[2],data[0],data[3],data[1]};
 assert(s3_pp_init(&p,buffers)==S3_PP_OK);
}
static void fill(unsigned bank,unsigned first,unsigned n,uint64_t seq) {
 for(unsigned i=0;i<n;++i)source[bank][(first+i)%S3_PP_WORDS]=sample(seq+i)|0xabc00000u;
}
static void *worker(void *arg) {
 unsigned w=(unsigned)(uintptr_t)arg,n;
 while(!atomic_load_explicit(&stop_flag,memory_order_relaxed)) {
  int rc=s3_pp_step(&p,w,w?127:113,0,1,&n);
  assert(rc==S3_PP_OK || rc==S3_PP_EMPTY);
  sched_yield();
 }
 return NULL;
}
static void finish_jobs(void) {
 unsigned n;
 for(unsigned w=0;w<2;++w)while(s3_pp_step(&p,w,8192,0,1,&n)==S3_PP_OK){}
 assert(s3_pp_collect(&p,0)==S3_PP_OK);
}
static void negatives(void) {
 init();fill(0,16380,11,0);
 assert(s3_pp_accept(&p,0,source[0],16380,11,0,0,100)==S3_PP_OK);
 assert(s3_pp_reclaim(&p,0)==S3_PP_BUSY);
 unsigned n;assert(s3_pp_step(&p,0,8192,0,1,&n)==S3_PP_OK);
 assert(s3_pp_collect(&p,0)==S3_PP_OK && p.published==0);
 assert(s3_pp_reclaim(&p,0)==S3_PP_BUSY);
 finish_jobs();assert(s3_pp_reclaim(&p,0)==S3_PP_OK);
 assert(p.have_carry && p.carry==sample(10) && p.published==25);
 init();assert(s3_pp_accept(&p,0,source[0],0,2,1,0,100)==S3_PP_SEQUENCE);
 assert(s3_pp_step(&p,0,1,0,1,&n)==S3_PP_FAULT);
 init();assert(s3_pp_accept(&p,0,source[0],0,2,0,0,100)==S3_PP_OK);
 assert(s3_pp_step(&p,1,1,99,1,&n)==S3_PP_DEADLINE && n==0);
 init();assert(s3_pp_accept(&p,0,source[0],0,2,0,0,100)==S3_PP_OK);
 assert(s3_pp_collect(&p,100)==S3_PP_DEADLINE);
 // Reserve almost the entire ring; two bytes remain, insufficient for a pair.
 init();uint64_t total=0;
 for(unsigned b=0;b<3;++b) {
  fill(b,0,16384,total);
  assert(s3_pp_accept(&p,b,source[b],0,16384,total,0,100)==S3_PP_OK);total+=16384;
 }
 finish_jobs();fill(0,0,3276,total);
 assert(s3_pp_accept(&p,0,source[0],0,3276,total,0,100)==S3_PP_OK);total+=3276;
 finish_jobs();assert(p.reserved==131070);
 uint64_t seq[3];const uint8_t *payload[3];
 for(unsigned i=0;i<3;++i)assert(s3_pp_take(&p,&seq[i],&payload[i])==S3_PP_OK);
 assert(s3_pp_complete(&p,seq[1])==S3_PP_OK && p.retired==0);
 assert(s3_pp_complete(&p,seq[1])==S3_PP_STALE);
 assert(s3_pp_accept(&p,0,source[0],0,2,total,0,100)==S3_PP_BUSY);
 assert(p.next_sample==total);
 for(unsigned i=0;i<3;++i)for(unsigned k=0;k<S3_PP_CHUNK;++k)
  assert(payload[i][k]==byte(seq[i]*S3_PP_CHUNK+k));
 assert(s3_pp_complete(&p,seq[0])==S3_PP_OK && p.retired==2);
 assert(s3_pp_complete(&p,seq[0])==S3_PP_STALE);
 fill(0,0,2,total);
 assert(s3_pp_accept(&p,0,source[0],0,2,total,0,100)==S3_PP_OK);
 assert(s3_pp_complete(&p,seq[2])==S3_PP_OK);
 uint8_t *overlap[4]={data[0],data[0],data[2],data[3]};
 assert(s3_pp_init(&p,overlap)==S3_PP_INVALID);
 puts("PASS partial-worker, deadline, backpressure, out-of-order DMA, stale lease");
}
static void concurrent(unsigned banks) {
 init();atomic_init(&stop_flag,0);pthread_t workers[2];
 for(unsigned w=0;w<2;++w)assert(pthread_create(&workers[w],NULL,worker,(void*)(uintptr_t)w)==0);
 uint64_t total=0,checked=0,seq[2]={0};const uint8_t *payload[2]={0};
 unsigned delay[2]={0},done=0,pending=0,first=0,n=0;bool live[2]={false,false};
 uint32_t rng=777;unsigned loops=0;
 while(done<banks || p.count || live[0] || live[1] || p.submitted<p.published/S3_PP_CHUNK) {
  assert(++loops<100000000);
  assert(s3_pp_collect(&p,0)==S3_PP_OK);
  for(unsigned port=0;port<2;++port) {
   if(live[port] && !delay[port]--) {
    for(unsigned k=0;k<S3_PP_CHUNK;++k)assert(payload[port][k]==byte(seq[port]*S3_PP_CHUNK+k));
    checked+=S3_PP_CHUNK;assert(s3_pp_complete(&p,seq[port])==S3_PP_OK);live[port]=false;
   }
   if(!live[port] && s3_pp_take(&p,&seq[port],&payload[port])==S3_PP_OK) {
    live[port]=true;delay[port]=port?2:23;
   }
  }
  if(done<banks) {
   unsigned bank=done%3;
   if(!pending && s3_pp_reclaim(&p,bank)==S3_PP_OK) {
    rng=rng*1664525+1013904223;first=(rng>>8)%S3_PP_WORDS;
    n=done%13==0?1:12287+(rng%67);fill(bank,first,n,total);pending=1;
   }
   if(pending) {
    int rc=s3_pp_accept(&p,bank,source[bank],first,n,total,0,100);
    assert(rc==S3_PP_OK || rc==S3_PP_BUSY);
    if(rc==S3_PP_OK) {total+=n;++done;pending=0;}
   }
  }
  sched_yield();
 }
 atomic_store_explicit(&stop_flag,1,memory_order_relaxed);
 for(unsigned w=0;w<2;++w)pthread_join(workers[w],NULL);
 assert(p.published==(total/2)*5 && checked==p.retired*S3_PP_CHUNK);
 assert(p.have_carry==(bool)(total%2));
 if(p.have_carry)assert(p.carry==sample(total-1));
 for(uint64_t at=checked;at<p.published;++at)
  assert(p.buffers[(at/S3_PP_CHUNK)%4][at%S3_PP_CHUNK]==byte(at));
 printf("PASS concurrent banks=%u samples=%llu checked_DMA_bytes=%llu tail_bytes=%llu metadata_bytes=%zu\n",
  banks,(unsigned long long)total,(unsigned long long)checked,(unsigned long long)(p.published-checked),sizeof(p));
}
static void variable_bank_slices(void) {
 for(unsigned carry=0;carry<2;++carry)for(unsigned large=0;large<2;++large){
  init();
  if(carry){fill(1,0,1,0);assert(s3_pp_accept(&p,1,source[1],0,1,0,0,100)==S3_PP_OK);finish_jobs();}
  unsigned count=large?14352:12288;
  fill(0,16380,count,carry);
  assert(s3_pp_accept(&p,0,source[0],16380,count,carry,0,100)==S3_PP_OK);
  for(unsigned w=0;w<2;++w){
   unsigned pairs=(count+carry)/2,cut=pairs*S3_PP_CORE0_SIXTEENTHS/16;
   unsigned expected=w?pairs-cut:cut;
   assert(p.banks[0].jobs[w].begin==(w?cut:0));
   assert(p.banks[0].jobs[w].end==(w?pairs:cut));
   unsigned calls=0,n;int rc;
   while((rc=s3_pp_step(&p,w,512,0,1,&n))==S3_PP_OK){assert(n&&n<=512);++calls;}
   assert(rc==S3_PP_EMPTY&&calls==(expected+511)/512);
  }
  assert(s3_pp_collect(&p,0)==S3_PP_OK);
  for(uint64_t at=0;at<p.published;++at)
   assert(p.buffers[(at/S3_PP_CHUNK)%4][at%S3_PP_CHUNK]==byte(at));
 }
 puts("PASS actual partition and 512-pair slice counts: nominal/maximum banks, carry and source wrap");
}
static void oldest_bank_service(void) {
 init();const unsigned order[3]={2,0,1};
 for(unsigned i=0;i<3;++i){
  unsigned b=order[i];fill(b,16380,14352,(uint64_t)i*14352);
  assert(s3_pp_accept(&p,b,source[b],16380,14352,(uint64_t)i*14352,0,100)==S3_PP_OK);
 }
 for(unsigned w=0;w<2;++w){
 unsigned cut=7176*S3_PP_CORE0_SIXTEENTHS/16;
 unsigned calls=((w?7176-cut:cut)+511)/512;
 for(unsigned call=0;call<3*calls;++call){
  unsigned before[3],n;
  for(unsigned b=0;b<3;++b)before[b]=p.banks[b].jobs[w].cursor;
  assert(s3_pp_step(&p,w,512,0,1,&n)==S3_PP_OK&&n);
  for(unsigned b=0;b<3;++b)
   assert(p.banks[b].jobs[w].cursor==before[b]+(b==order[call/calls]?n:0));
 }
 }
 for(unsigned w=0;w<2;++w){unsigned n;assert(s3_pp_step(&p,w,512,0,1,&n)==S3_PP_EMPTY);}
 assert(s3_pp_collect(&p,0)==S3_PP_OK&&p.count==0&&p.published==107640);
 for(uint64_t at=0;at<p.published;++at)
  assert(p.buffers[(at/S3_PP_CHUNK)%4][at%S3_PP_CHUNK]==byte(at));
 puts("PASS 3 maximum banks: partition-dependent slice counts in sequence order 2/0/1, not bank index order; full output exact");
}
static void native_size_output_retirement(void) {
 init();uint64_t total=0;
 for(unsigned i=0;i<3;++i){
  fill(i,0,14352,total);
  assert(s3_pp_accept(&p,i,source[i],0,14352,total,0,100)==S3_PP_OK);
  total+=14352;finish_jobs();
  assert(s3_pp_reclaim(&p,i)==S3_PP_OK && p.count==0);
 }
 assert(p.reserved==107640 && p.published==107640);
 uint64_t seq[2];const uint8_t *payload[2];
 for(unsigned i=0;i<2;++i)assert(s3_pp_take(&p,&seq[i],&payload[i])==S3_PP_OK);
 assert(s3_pp_complete(&p,seq[1])==S3_PP_OK && p.retired==0);
 fill(0,0,14352,total);
 assert(s3_pp_accept(&p,0,source[0],0,14352,total,0,100)==S3_PP_BUSY);
 assert(p.count==0 && p.next_sample==total && !atomic_load(&p.fault));
 for(unsigned k=0;k<S3_PP_CHUNK;++k)assert(payload[0][k]==byte(k));
 assert(s3_pp_complete(&p,seq[0])==S3_PP_OK && p.retired==2);
 assert(s3_pp_accept(&p,0,source[0],0,14352,total,0,100)==S3_PP_OK);
 finish_jobs();assert(p.reserved==143520);
 for(uint64_t at=p.retired*S3_PP_CHUNK;at<p.published;++at)
  assert(p.buffers[(at/S3_PP_CHUNK)%4][at%S3_PP_CHUNK]==byte(at));
 puts("PASS native-sized banks: all RF banks reclaimed but fourth reservation blocked until ordered DMA retirement");
}
int main(int argc,char **argv) {negatives();variable_bank_slices();oldest_bank_service();native_size_output_retirement();concurrent(argc>1?(unsigned)atoi(argv[1]):2000);return 0;}

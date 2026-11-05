/* Actual budgeted RF owner, independent write-set oracle. No real RF timing. */
#include "s3_native_capture.c"
#include <assert.h>
#include <stdio.h>
static uint32_t words[16386];
static unsigned reclaim_calls,bank_calls,index_value;static bool reclaim_ok,available;
static uint32_t rd_mock(void *c,uint32_t a){(void)c;assert(a==INDEX);return index_value;}
static void wr_mock(void *c,uint32_t a,uint32_t v){(void)c;(void)v;assert(a==CTRL||a==SELECT);}
static uint32_t ticks(void *c){(void)c;return 0;}
static uint32_t *bank_mock(void*c,unsigned b){(void)c;assert(b==1);assert(reclaim_calls==1);++bank_calls;return words+1;}
static bool healthy(void*c){(void)c;return true;}
static bool avail(void*c,unsigned b){(void)c;assert(b==1);return available;}
static bool reclaim(void*c,unsigned b){(void)c;assert(b==1);++reclaim_calls;for(unsigned i=0;i<16386;++i)assert(words[i]==i);return reclaim_ok;}
static bool accept_mock(void*c,unsigned b,const uint32_t*w,unsigned f,unsigned n,uint64_t i,uint64_t t,uint64_t d){(void)c;(void)b;(void)w;(void)f;(void)n;(void)i;(void)t;(void)d;assert(0);return false;}
static s3_native_capture init(unsigned expected){
 for(unsigned i=0;i<16386;++i)words[i]=i;
 reclaim_calls=bank_calls=0;available=reclaim_ok=true;index_value=expected;
 s3_native_capture s={0};s.running=true;s.cpp=6;s.expected=expected;
 s.io=(s3_native_io){rd_mock,wr_mock,ticks,bank_mock,0};
 s.sink=(s3_native_sink){words,healthy,avail,reclaim,accept_mock};return s;
}
static void check(const s3_native_capture*s,unsigned done){
 assert(words[0]==0&&words[16385]==16385);
 for(unsigned k=0;k<16384;++k){
  unsigned distance=(k+16384-s->start[1])%16384;
  bool touched=distance<(done<START?done:START)||(done>START&&distance>=THRESHOLD&&distance<THRESHOLD+done-START);
  assert(words[k+1]==(touched?SENTINEL:k+1));
 }
}
int main(void){
 for(unsigned origin=0;origin<16384;++origin){
  s3_native_capture s=init(origin);
  unsigned zero=0;assert(s3_native_poll_budget(&s,&zero));assert(!s.prepared&&s.preparing&&!s.prepare_done&&reclaim_calls==1&&!bank_calls);
  for(unsigned q=1;q<=7;++q){
   unsigned budget=1024;assert(s3_native_poll_budget(&s,&budget));assert(!budget&&s.prepare_done==q*1024);
   assert(s.prepared==(q==7));assert(s.preparing==(q!=7));assert(reclaim_calls==1);
   assert(s3_native_poll_budget(&s,&budget));assert(s.prepare_done==q*1024); // same iteration's empty budget
   if(origin%1024==0)check(&s,q*1024);
  }
  assert(bank_calls==7);check(&s,START+END);
 }
 const unsigned quanta[]={1,7,31,1023,1536,4096,8000};
 for(unsigned q=0;q<sizeof quanta/sizeof *quanta;++q){
  s3_native_capture s=init(16383);unsigned done=0;
  while(!s.prepared){unsigned b=quanta[q],before=b;assert(s3_native_poll_budget(&s,&b));done+=before-b;assert(s.prepare_done==done);check(&s,done);}
  assert(done==START+END&&reclaim_calls==1);
 }
 s3_native_capture s=init(0);unsigned b=1024;assert(s3_native_poll_budget(&s,&b));index_value=THRESHOLD;b=1024;
 assert(!s3_native_poll_budget(&s,&b)&&s.fault==5&&!s.running);assert(s.prepare_done==1024);check(&s,1024);
 s=init(0);reclaim_ok=false;b=1024;assert(!s3_native_poll_budget(&s,&b)&&s.fault==6&&!bank_calls);
 s=init(0);available=false;b=1024;assert(s3_native_poll_budget(&s,&b)&&b==1024&&!reclaim_calls&&!bank_calls&&!s.preparing);
 puts("PASS budgeted production poll: 16384 origins, partial writes/zero budget, 7 quanta, variable quanta, reclaim once, incomplete-preparation deadline stop and reclaim failure");
}

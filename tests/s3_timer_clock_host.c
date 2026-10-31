#include "s3_timer_clock.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
enum {CTRL=0x60033d5c,INDEX=0x60033d60,SELECT=0x600c101c};
#define SENTINEL UINT32_C(0xa5c33c5a)
static uint32_t words[16384],select_value;
static uint64_t physical,accepted_deadline;
static unsigned accepts,script_reads;
static int64_t script[2];static bool scripted;
int64_t esp_timer_get_time(void){return scripted?script[script_reads++?1:0]:(int64_t)(physical/240);}
static uint32_t rd(void*c,uint32_t a){(void)c;return a==SELECT?select_value:0;}
static void wr(void*c,uint32_t a,uint32_t v){(void)c;if(a==SELECT)select_value=v;}
static uint32_t*bank(void*c,unsigned b){(void)c;(void)b;return words;}
static bool healthy(void*c){(void)c;return true;}
static bool available(void*c,unsigned b){(void)c;(void)b;return true;}
static bool accept(void*c,unsigned b,const uint32_t*w,unsigned f,unsigned n,uint64_t i,uint64_t now,uint64_t deadline){
 (void)c;(void)b;(void)w;(void)f;(void)n;(void)i;assert(now>=physical&&now-physical<=240);++accepts;accepted_deadline=deadline;return true;
}
static _Alignas(16) uint8_t data[4][S3_PP_CHUNK];
static void init_pack(s3_parallel_pack*p,uint64_t deadline){
 uint8_t*buffers[4]={data[0],data[1],data[2],data[3]};
 assert(s3_pp_init(p,buffers)==S3_PP_OK);assert(s3_pp_accept(p,0,words,0,16,0,24000,deadline)==S3_PP_OK);
}
int main(void){
 assert(s3_timer_clock_upper(-1)==UINT64_MAX);
 assert(s3_timer_clock_upper(INT64_MAX)==UINT64_MAX);
 assert(s3_timer_clock_upper(0)==240);
 assert(s3_timer_clock_upper((int64_t)(UINT64_MAX/240-1))!=UINT64_MAX);
 assert(s3_timer_clock_upper((int64_t)(UINT64_MAX/240))==UINT64_MAX);
 const uint64_t epoch=UINT64_C(1000000)*240;
 unsigned cases=0;
 for(unsigned rate=16;rate<=40;rate+=24)for(unsigned phase=0;phase<240;++phase){
  physical=epoch+phase;scripted=false;accepts=0;
  s3_native_capture s={0};s3_native_io io={rd,wr,NULL,bank,NULL};s3_native_sink sink={&physical,healthy,available,available,accept};
  assert(s3_native_start_sink_clocked(&s,sink,io,rate,s3_timer_clock,NULL,240));
  assert(s.switch_earliest<=physical&&s.switched>=physical);
  s.settling=true;s.unit=1;s.active=0;s.start[0]=0;s.end[0]=12288;s.write_index=12290;s.expected=1;
  for(unsigned k=0;k<16384;++k)words[k]=SENTINEL;
  for(unsigned k=1;k<12290;++k)words[k]=k;
  const uint64_t physical_switch=physical,lease=2*12288*s.cpp-20000-3024*s.cpp;
  for(unsigned delta=0;delta<=720;++delta){
   s3_native_capture trial=s;physical=physical_switch+delta;accepts=0;
   assert(s3_native_poll(&trial));
   if(accepts){assert(delta>=16*s.cpp);assert(accepted_deadline<=physical_switch+lease);}
   if(delta>=720)assert(accepts==1);
   ++cases;
  }
  // Upper elapsed age rejects at/beyond the physical maximum, even at adverse phase.
  s3_native_capture aged=s;physical=physical_switch+(16384-128)*s.cpp+1;accepts=0;
  assert(!s3_native_poll(&aged)&&aged.fault==4&&!accepts);
 }
 // Same callback used by the real worker wrapper: timestamp difference alone
 // undercounts an interval by up to 240 cycles. Bound 479 must reject delta 240.
 s3_parallel_pack p;unsigned processed;
 for(unsigned bound=479;bound<=480;++bound){
  init_pack(&p,26000);scripted=true;script[0]=100;script[1]=101;script_reads=0;
  int r=s3_pp_step_timer(&p,0,4,bound,&processed);
  assert(r==(bound==479?S3_PP_DEADLINE:S3_PP_OK));
  if(bound==479)assert(p.banks[0].owned&&p.published==0);
 }
 init_pack(&p,24480);scripted=true;script[0]=100;script[1]=100;script_reads=0;
 assert(s3_pp_step_timer(&p,0,4,241,&processed)==S3_PP_DEADLINE&&processed==0);
 init_pack(&p,26000);script[0]=-1;script_reads=0;
 assert(s3_pp_step_timer(&p,0,4,480,&processed)==S3_PP_DEADLINE&&processed==0);
 scripted=false;physical=epoch;
 uint8_t*buffers[4]={data[0],data[1],data[2],data[3]};assert(s3_pp_init(&p,buffers)==S3_PP_OK);
 s3_native_capture s={0};s3_native_io io={rd,wr,NULL,bank,NULL};
 assert(s3_pp_native_start_timer(&s,&p,io,40));assert(s.common_clock==s3_timer_clock&&s.clock_error==240);
 s3_native_stop(&s);
 printf("PASS actual SDK adapter + native/worker interval compensation: %u phase/elapsed cases; stale/overflow/bound/deadline checks\n",cases);
}

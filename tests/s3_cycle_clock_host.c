#include "s3_cycle_clock.h"
#include <assert.h>
#include <stdio.h>
static unsigned timer_reads,cpu_reads;
static uint64_t physical,offset;
int64_t esp_timer_get_time(void){++timer_reads;physical+=73;return (int64_t)(physical/240);}
uint32_t esp_cpu_get_cycle_count(void){++cpu_reads;return (uint32_t)(physical+offset);}
static void bracket(const s3_cycle_clock_state*s,uint64_t actual,uint64_t u){
 assert(u>=s->error);assert(u-s->error<=actual && actual<=u);
}
int main(void){
 unsigned cases=0;
 for(unsigned phase=0;phase<240;++phase)
 for(unsigned delay=0;delay<=720;delay+=9)
 for(unsigned which=0;which<3;++which)
 for(unsigned near_wrap=0;near_wrap<2;++near_wrap){
  uint64_t start=UINT64_C(90000000000)+phase;
  unsigned sample_delta=which==0?0:which==1?delay/2:delay;
  uint32_t c0=near_wrap?UINT32_MAX-100:12345;
  s3_cycle_clock_state s={0};
  assert(s3_cycle_clock_calibrate(&s,start/240,c0,(start+sample_delta)/240,
    c0+delay,(start+delay)/240));
  assert(s.error==delay+240);bracket(&s,start+delay,s.upper);
  uint64_t elapsed=0,previous=s.upper;
  const uint32_t gaps[]={0,1,240,UINT32_MAX-100,12345,1};
  for(unsigned n=0;n<sizeof(gaps)/sizeof(*gaps);++n){
   elapsed+=gaps[n];uint64_t u=s3_cycle_clock_advance(&s,c0+delay+(uint32_t)elapsed);
   assert(u==previous+gaps[n]);bracket(&s,start+delay+elapsed,u);previous=u;
  }
  ++cases;
 }
 s3_cycle_clock_state s={0};
 assert(!s3_cycle_clock_calibrate(&s,-1,0,0,0,0));
 assert(!s3_cycle_clock_calibrate(&s,2,0,1,0,3));
 assert(!s3_cycle_clock_calibrate(&s,0,0,2,0,1));
 assert(!s3_cycle_clock_calibrate(&s,0,0,0,0,17895697));
 assert(!s3_cycle_clock_calibrate(&s,0,0,0,241,0));
 assert(!s3_cycle_clock_calibrate(&s,INT64_MAX,0,INT64_MAX,0,INT64_MAX));
 assert(s3_cycle_clock_advance(&s,0)==UINT64_MAX);
 s=(s3_cycle_clock_state){UINT64_MAX-1,0,240,true};
 assert(s3_cycle_clock_advance(&s,2)==UINT64_MAX&&!s.valid);
 assert(!s3_cycle_clock_calibrate(NULL,0,0,0,0,0));
 assert(s3_cycle_clock_advance(NULL,0)==UINT64_MAX);
 /* The real ESP adapter is linked with SDK reads mocked. Independently offset
  * core counters, startup calls only; runtime never calls esp_timer_get_time. */
 s3_cycle_clock_state cores[2];
 for(unsigned i=0;i<2;++i){
  physical=UINT64_C(90000000000);offset=i?UINT32_MAX-1000:1234;
  assert(s3_cycle_clock_init(&cores[i]));assert(cores[i].error==313);
 }
 unsigned reads=timer_reads;
 for(unsigned i=0;i<2;++i){
  physical=UINT64_C(90000000000)+100000;offset=i?UINT32_MAX-1000:1234;
  bracket(&cores[i],physical,s3_cycle_clock_read(&cores[i]));
 }
 assert(timer_reads==reads&&reads==6&&cpu_reads==6);
 printf("PASS %u calibration phase/latency/offset cases; wrap, overflow, two-core epoch, no runtime SYSTIMER reads\n",cases);
}

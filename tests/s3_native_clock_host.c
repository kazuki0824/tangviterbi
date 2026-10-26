#include "s3_native_capture.c"
#include <assert.h>
#include <stdio.h>
static struct {uint32_t words[16384],select,index;uint64_t time;unsigned reads,bad,accepts,index_reads;bool enabled,bank_busy;} hw;
static uint32_t mock_read(void*c,uint32_t a){(void)c;if(a==INDEX){++hw.index_reads;return hw.index;}return a==SELECT?hw.select:0;}
static void mock_write(void*c,uint32_t a,uint32_t v){(void)c;if(a==CTRL)hw.enabled=(v>>31)!=0;if(a==SELECT)hw.select=v;}
static uint32_t *bank(void*c,unsigned b){(void)c;(void)b;return hw.words;}
static uint64_t timer(void*c){(void)c;++hw.reads;return hw.reads==hw.bad?UINT64_MAX:hw.time;}
static bool yes(void*c){(void)c;return true;}
static bool yesbank(void*c,unsigned b){(void)c;(void)b;return !hw.bank_busy;}
static bool accept(void*c,unsigned b,const uint32_t*w,unsigned f,unsigned n,uint64_t i,uint64_t t,uint64_t d){
 (void)c;(void)b;(void)w;(void)f;(void)n;(void)i;assert(t==hw.time);assert(d>t);++hw.accepts;return true;
}
static s3_native_capture start_rate(unsigned bad,unsigned rate){
 memset(&hw,0,sizeof(hw));hw.time=(UINT64_C(1)<<40)+123;hw.select=7;hw.bad=bad;
 s3_native_capture s={0};s3_native_io io={mock_read,mock_write,NULL,bank,NULL};s3_native_sink sink={&hw,yes,yesbank,yesbank,accept};
 bool ok=s3_native_start_sink_clocked(&s,sink,io,rate,timer,NULL,0);
 assert(ok==(bad!=1&&bad!=2));
 if(!ok)assert(!s.running&&!hw.enabled&&hw.select==7&&s.fault==S3_NATIVE_CLOCK_FAULT);
 return s;
}
static s3_native_capture start(unsigned bad){return start_rate(bad,40);}
static s3_native_capture settled(unsigned rate){
 s3_native_capture s=start_rate(0,rate);hw.time+=16*s.cpp;
 s.settling=true;s.unit=1;s.active=0;s.start[0]=0;s.end[0]=12288;s.write_index=12290;s.expected=1;
 for(unsigned k=0;k<16384;++k)hw.words[k]=SENTINEL;
 for(unsigned k=1;k<12290;++k)hw.words[k]=k;
 assert(s3_native_poll(&s)&&!s.settling&&hw.accepts==1&&!s.prepared);
 return s;
}
int main(void){
 start(1);start(2);
 for(unsigned position=3;position<=4;++position){
  s3_native_capture s=start(position);
  assert(!s3_native_poll(&s));assert(s.fault==S3_NATIVE_CLOCK_FAULT&&!s.running&&!hw.enabled&&hw.select==7);
  assert(hw.accepts==0);
 }
 s3_native_capture s=start(0);uint64_t before=s.now;
 --hw.time;assert(!s3_native_poll(&s));assert(s.now==before&&s.fault==S3_NATIVE_CLOCK_FAULT&&!hw.enabled);
 s=start(0);hw.time=UINT64_MAX-2*12288*6+1;
 assert(!s3_native_poll(&s));assert(s.fault==S3_NATIVE_CLOCK_FAULT&&!hw.enabled);
 s=start(0);hw.time=UINT64_MAX-2*12288*6;
 assert(clock_now(&s)==hw.time&&!s.fault); // arithmetic boundary itself valid
 s3_native_stop(&s);
 s=start(0);s.prepared=true;s.expected=(0u-12288)&16383;
 hw.bad=hw.reads+2; // failure in clock read after bank SELECT
 assert(!s3_native_poll(&s));assert(s.fault==S3_NATIVE_CLOCK_FAULT&&!hw.enabled&&!s.settling&&hw.select==7);
 for(unsigned point=2;point<=3;++point){
  s=start(0);hw.time+=96;
  s.settling=true;s.unit=1;s.active=0;s.start[0]=0;s.end[0]=12288;s.write_index=12290;s.expected=1;
  for(unsigned k=0;k<16384;++k)hw.words[k]=SENTINEL;
  for(unsigned k=1;k<12290;++k)hw.words[k]=k;
  hw.bad=hw.reads+point; // before accept or after successful accept
  assert(!s3_native_poll(&s));assert(s.fault==S3_NATIVE_CLOCK_FAULT&&!hw.enabled&&hw.accepts==point-2&&hw.select==7);
 }
 // Poll invocation count is not INDEX observation count. Ordinary polling
 // reads INDEX; both settling paths return without an INDEX read.
 s=start(0);unsigned observations=hw.index_reads;
 assert(s3_native_poll(&s)&&hw.index_reads==observations+1);
 s=start(0);observations=hw.index_reads;s.settling=true;
 hw.time+=95;assert(s3_native_poll(&s)&&s.settling&&hw.index_reads==observations);
 ++hw.time;s.unit=1;s.active=0;s.start[0]=0;s.end[0]=12288;s.write_index=12290;s.expected=1;
 for(unsigned k=0;k<16384;++k)hw.words[k]=SENTINEL;
 for(unsigned k=1;k<12290;++k)hw.words[k]=k;
 assert(s3_native_poll(&s)&&!s.settling&&hw.accepts==1&&hw.index_reads==observations);
 s3_native_stop(&s);
 puts("PASS observation distinction: ordinary poll reads INDEX; settling wait and settlement/accept do not");
 for(unsigned rate=16;rate<=40;rate+=24){
  s=settled(rate);unsigned gate=THRESHOLD-20000/s.cpp-1024-LATE;
  hw.bank_busy=true;hw.index=(s.expected+gate-1)&MASK;
  hw.time=s.switch_earliest+(uint64_t)(gate-1)*s.cpp;
  assert(s3_native_poll(&s)&&!s.prepared&&!s.fault);
  ++hw.index;hw.time+=s.cpp;
  assert(!s3_native_poll(&s)&&s.fault==7&&!hw.enabled);
  // The busy gate is not an unconditional limit: a free bank can be prepared
  // later, but never when the first unprepared observation is at THRESHOLD.
  s=settled(rate);hw.index=(s.expected+THRESHOLD-1)&MASK;
  hw.time=s.switch_earliest+(uint64_t)(THRESHOLD-1)*s.cpp;
  assert(s3_native_poll(&s)&&s.prepared);s3_native_stop(&s);
  s=settled(rate);hw.index=(s.expected+THRESHOLD)&MASK;
  hw.time=s.switch_earliest+(uint64_t)THRESHOLD*s.cpp;
  assert(!s3_native_poll(&s)&&s.fault==5&&!hw.enabled);
 }
 puts("PASS first post-settlement INDEX: T/S busy gate-1/gate and available THRESHOLD-1/THRESHOLD");
 puts("PASS common clock: startup/poll/switch/preaccept/postaccept failed reads, regression, deadline arithmetic boundary, RF stop and SELECT restore");
}

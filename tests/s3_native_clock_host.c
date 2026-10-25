#include "s3_native_capture.c"
#include <assert.h>
#include <stdio.h>
static struct {uint32_t words[16384],select;uint64_t time;unsigned reads,bad,accepts;bool enabled;} hw;
static uint32_t mock_read(void*c,uint32_t a){(void)c;return a==SELECT?hw.select:0;}
static void mock_write(void*c,uint32_t a,uint32_t v){(void)c;if(a==CTRL)hw.enabled=(v>>31)!=0;if(a==SELECT)hw.select=v;}
static uint32_t *bank(void*c,unsigned b){(void)c;(void)b;return hw.words;}
static uint64_t timer(void*c){(void)c;++hw.reads;return hw.reads==hw.bad?UINT64_MAX:hw.time;}
static bool yes(void*c){(void)c;return true;}
static bool yesbank(void*c,unsigned b){(void)c;(void)b;return true;}
static bool accept(void*c,unsigned b,const uint32_t*w,unsigned f,unsigned n,uint64_t i,uint64_t t,uint64_t d){
 (void)c;(void)b;(void)w;(void)f;(void)n;(void)i;assert(t==hw.time);assert(d>t);++hw.accepts;return true;
}
static s3_native_capture start(unsigned bad){
 memset(&hw,0,sizeof(hw));hw.time=(UINT64_C(1)<<40)+123;hw.select=7;hw.bad=bad;
 s3_native_capture s={0};s3_native_io io={mock_read,mock_write,NULL,bank,NULL};s3_native_sink sink={&hw,yes,yesbank,yesbank,accept};
 bool ok=s3_native_start_sink_clocked(&s,sink,io,40,timer,NULL,0);
 assert(ok==(bad!=1&&bad!=2));
 if(!ok)assert(!s.running&&!hw.enabled&&hw.select==7&&s.fault==S3_NATIVE_CLOCK_FAULT);
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
 puts("PASS common clock: startup/poll/switch/preaccept/postaccept failed reads, regression, deadline arithmetic boundary, RF stop and SELECT restore");
}

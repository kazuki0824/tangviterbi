/* Native bank handoff derived from ESPARGOS/esp-sdr e74f2a470972ec163c247f1fe88d32e08579242a,
 * main/common/ring_capture.c, GPL-3.0. This adaptation preserves every sample,
 * fails on reclaim/age/boundary errors, and does not mask interrupts or reset core1.
 * PIE sentinel fill in upstream credits h0m3us3r/eSpDR (0BSD).
 * This portable implementation is a correctness baseline, not a WCET claim.
 */
#include "s3_native_capture.h"
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#include "esp_cpu.h"
#include "soc/soc.h"
#define HOT IRAM_ATTR
#else
#define HOT
#endif
enum { CTRL=0x60033d5c, INDEX=0x60033d60, CONFIG=0x60033d90, SELECT=0x600c101c,
 MASK=16383, THRESHOLD=12288, START=3072, END=4096, LATE=2000 };
#define SENTINEL UINT32_C(0xa5c33c5a)
static uint64_t HOT clock_now(s3_native_capture *s) {
 uint32_t t=s->io.cycles(s->io.ctx);s->now+=(uint32_t)(t-s->last_clock);s->last_clock=t;return s->now;
}
static void HOT wr(s3_native_capture*s,uint32_t a,uint32_t v){s->io.write(s->io.ctx,a,v);}
static uint32_t HOT rd(s3_native_capture*s,uint32_t a){return s->io.read(s->io.ctx,a);}
static void HOT fill(s3_native_capture*s,unsigned b,unsigned at,unsigned n) {
 volatile uint32_t *p=s->io.bank(s->io.ctx,b);
 // Keep the same volatile stores and order, but mask only at ring wraps.
 at&=MASK;
 while(n){
  unsigned span=MASK+1-at;if(span>n)span=n;
  volatile uint32_t *dst=p+at;
  for(unsigned i=0;i<span;++i)*dst++=SENTINEL;
  n-=span;at=0;
 }
#ifdef ESP_PLATFORM
 __asm__ volatile("memw" ::: "memory");
#endif
}
void HOT s3_native_stop(s3_native_capture*s){
 if(s&&s->running){wr(s,CTRL,0);wr(s,SELECT,s->saved);s->running=false;}
}
static bool HOT fail(s3_native_capture*s,unsigned fault){s->fault=fault;s3_native_stop(s);return false;}
static unsigned HOT first(s3_native_capture*s,unsigned b,unsigned origin,unsigned guard){
 const volatile uint32_t*p=s->io.bank(s->io.ctx,b);
 if(p[origin&MASK]!=SENTINEL||p[(origin+guard-1)&MASK]==SENTINEL)return UINT32_MAX;
 unsigned lo=0,hi=guard-1;
 while(lo<hi){unsigned m=(lo+hi)/2;if(p[(origin+m)&MASK]==SENTINEL)lo=m+1;else hi=m;}
 return (origin+lo)&MASK;
}
static unsigned HOT end(s3_native_capture*s,unsigned b,unsigned origin,unsigned w,unsigned guard){
 const volatile uint32_t*p=s->io.bank(s->io.ctx,b);unsigned lo=(w-origin)&MASK,hi=guard-1;
 if(lo>=guard||p[(origin+hi)&MASK]!=SENTINEL)return UINT32_MAX;
 while(lo<hi){unsigned m=(lo+hi)/2;if(p[(origin+m)&MASK]==SENTINEL)hi=m;else lo=m+1;}
 return (origin+lo)&MASK;
}
static bool HOT bridge_healthy(void *ctx){s3_capture_bridge*b=ctx;return !b->fault;}
static bool HOT bridge_available(void *ctx,unsigned n){s3_capture_bridge*b=ctx;return !b->banks[n].owned;}
static bool HOT bridge_reclaim(void *ctx,unsigned n){return s3_capture_reclaim(ctx,n);}
static bool HOT bridge_accept(void *ctx,unsigned n,const uint32_t*w,unsigned f,unsigned c,uint64_t i,uint64_t t,uint64_t d){
 return s3_capture_accept(ctx,n,w,f,c,i,t,d);
}
bool s3_native_start(s3_native_capture*s,s3_capture_bridge*b,s3_native_io io,unsigned rate){
 if(!b || b->fault || b->count)return false;
 s3_native_sink sink={b,bridge_healthy,bridge_available,bridge_reclaim,bridge_accept};
 bool ok=s3_native_start_sink(s,sink,io,rate);
 if(ok)s->bridge=b;
 return ok;
}
bool s3_native_start_sink(s3_native_capture*s,s3_native_sink sink,s3_native_io io,unsigned rate){
 if(!s||s->running||!sink.ctx||!sink.healthy||!sink.available||!sink.reclaim||!sink.accept||
    !sink.healthy(sink.ctx)||!io.read||!io.write||!io.cycles||!io.bank||(rate!=16&&rate!=40))return false;
 for(unsigned b=0;b<3;++b)if(!sink.available(sink.ctx,b))return false;
 memset(s,0,sizeof(*s));s->sink=sink;s->io=io;s->cpp=240/rate;s->saved=rd(s,SELECT);
 s->ctrl=0x24000|(rate==16?1u<<16:1u<<15);
 wr(s,CTRL,0);for(unsigned i=0;i<3;++i)fill(s,i,0,16384);
 wr(s,CONFIG,0xc2040);wr(s,CTRL,s->ctrl);wr(s,SELECT,(s->saved&~15u)|1u);
 s->last_clock=io.cycles(io.ctx);s->running=true;
 wr(s,CTRL,s->ctrl|0x80000000u);s->w0=rd(s,INDEX)&MASK;s->expected=(s->w0-256)&MASK;
 s->switched=clock_now(s);return true;
}
bool HOT s3_native_poll(s3_native_capture*s){
 if(!s||!s->running||s->fault)return false;
 uint64_t now=clock_now(s);unsigned b=s->active,next=(b+1)%3;
 if(!s->sink.healthy(s->sink.ctx))return fail(s,1);
 if(s->settling){
  if(now-s->switched>(16384-128)*s->cpp)return fail(s,4);
  if(now-s->switched<16*s->cpp)return true;
  unsigned f=first(s,b,s->unit?s->start[b]:(s->w0-1024)&MASK,START);
  unsigned e=end(s,b,s->unit?s->end[b]:s->write_index,s->write_index,s->unit?END:1024);
  unsigned count=(e-f)&MASK;
  if(f==UINT32_MAX||e==UINT32_MAX||(s->unit&&f!=s->expected)||
     count<(s->unit?THRESHOLD:THRESHOLD-1024)||count>THRESHOLD+LATE+64)return fail(s,2);
  uint64_t deadline=s->switched+2*THRESHOLD*s->cpp-20000-(1024+LATE)*s->cpp;
  now=clock_now(s);
  if(!s->sink.accept(s->sink.ctx,b,s->io.bank(s->io.ctx,b),f,count,s->index,now,deadline))return fail(s,3);
  s->index+=count;s->expected=e;s->active=next;++s->unit;s->prepared=false;s->settling=false;
  clock_now(s);return true;
 }
 if(now-s->switched>(16384-128)*s->cpp)return fail(s,4);
 unsigned w=rd(s,INDEX)&MASK,written=(w-s->expected)&MASK;
 if(written>=THRESHOLD){
  if(!s->prepared||written>THRESHOLD+LATE)return fail(s,5);
  s->write_index=w;wr(s,SELECT,(s->saved&~15u)|(1u<<next));s->switched=clock_now(s);s->settling=true;return true;
 }
 if(!s->prepared){
  if(s->sink.available(s->sink.ctx,next)){
   // Reclaim BEFORE any sentinel write, even when the next bank seems idle.
   if(!s->sink.reclaim(s->sink.ctx,next))return fail(s,6);
   s->start[next]=(s->expected+THRESHOLD)&MASK;s->end[next]=(s->start[next]+THRESHOLD)&MASK;
   fill(s,next,s->start[next],START);fill(s,next,s->end[next],END);s->prepared=true;
  }else if(written+20000/s->cpp+1024+LATE>=THRESHOLD)return fail(s,7);
 }
 clock_now(s);return true;
}
#ifdef ESP_PLATFORM
static uint32_t HOT mmio_read(void*c,uint32_t a){(void)c;return REG_READ(a);}
static void HOT mmio_write(void*c,uint32_t a,uint32_t v){(void)c;REG_WRITE(a,v);}
static uint32_t HOT mmio_clock(void*c){(void)c;return esp_cpu_get_cycle_count();}
static uint32_t* HOT mmio_bank(void*c,unsigned b){(void)c;return (uint32_t*)(0x3fcb0000u+b*65536u);}
s3_native_io s3_native_mmio(void){return (s3_native_io){mmio_read,mmio_write,mmio_clock,mmio_bank,0};}
#endif

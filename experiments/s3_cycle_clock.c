#include "s3_cycle_clock.h"
#include <stddef.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#include "esp_cpu.h"
#include "esp_timer.h"
#define HOT IRAM_ATTR
#else
#define HOT
#endif
bool s3_cycle_clock_calibrate(s3_cycle_clock_state*s,int64_t before_us,
 uint32_t before_count,int64_t sample_us,uint32_t after_count,int64_t after_us) {
 if(!s)return false;
 s->valid=false;
 if(before_us<0 || sample_us<before_us || after_us<sample_us)return false;
 /* At most one counter wrap, including the uncertain endpoints. Reject a
  * long startup interruption instead of silently losing whole wraps. */
 uint64_t span=(uint64_t)after_us-(uint64_t)before_us;
 if(span>=(UINT64_C(1)<<32)/240)return false;
 uint64_t outer=(span+1)*240;
 if(outer>=(UINT64_C(1)<<32))return false;
 uint32_t delta=after_count-before_count;
 if(delta>outer || delta>UINT32_MAX-240)return false;
 if((uint64_t)sample_us>UINT64_MAX/240-1)return false;
 uint64_t upper=((uint64_t)sample_us+1)*240;
 if(upper>UINT64_MAX-delta)return false;
 s->upper=upper+delta;s->last=after_count;s->error=delta+240;s->valid=true;
 return true;
}
uint64_t HOT s3_cycle_clock_advance(s3_cycle_clock_state*s,uint32_t count) {
 if(!s || !s->valid)return UINT64_MAX;
 uint32_t elapsed=count-s->last;
 if(s->upper>UINT64_MAX-elapsed){s->valid=false;return UINT64_MAX;}
 s->last=count;s->upper+=elapsed;return s->upper;
}
#ifdef ESP_PLATFORM
bool s3_cycle_clock_init(s3_cycle_clock_state*s) {
 int64_t before=esp_timer_get_time();
 uint32_t c0=esp_cpu_get_cycle_count();
 int64_t sample=esp_timer_get_time();
 uint32_t c1=esp_cpu_get_cycle_count();
 int64_t after=esp_timer_get_time();
 return s3_cycle_clock_calibrate(s,before,c0,sample,c1,after);
}
uint64_t IRAM_ATTR s3_cycle_clock_read(void*ctx) {
 return s3_cycle_clock_advance(ctx,esp_cpu_get_cycle_count());
}
#endif

#include "s3_timer_clock.h"
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#include "esp_timer.h"
uint64_t IRAM_ATTR s3_timer_clock(void *ctx) {
 (void)ctx;return s3_timer_clock_upper(esp_timer_get_time());
}
bool s3_pp_native_start_timer(s3_native_capture*s,s3_parallel_pack*p,s3_native_io io,unsigned rate) {
 return s3_pp_native_start_clocked(s,p,io,rate,s3_timer_clock,NULL,S3_TIMER_CLOCK_ERROR);
}
int IRAM_ATTR s3_pp_step_timer(s3_parallel_pack*p,unsigned worker,unsigned max_pairs,uint64_t bound,unsigned*processed) {
 return s3_pp_step_clocked_quantized(p,worker,max_pairs,s3_timer_clock,NULL,S3_TIMER_CLOCK_ERROR,bound,processed);
}
#endif

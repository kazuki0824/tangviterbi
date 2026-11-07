#ifndef S3_TIMER_CLOCK_H
#define S3_TIMER_CLOCK_H
#include "s3_parallel_capture.h"
enum { S3_TIMER_CLOCK_ERROR=240 };
/* Upper endpoint of [us*240,(us+1)*240]; preserves the SDK boot epoch.
 * Negative/overflow time is a failed read. No shared per-core extension state.
 */
static inline uint64_t s3_timer_clock_upper(int64_t us) {
 if(us<0 || (uint64_t)us>UINT64_MAX/240-1)return UINT64_MAX;
 return ((uint64_t)us+1)*240;
}
#ifdef ESP_PLATFORM
uint64_t s3_timer_clock(void*);
bool s3_pp_native_start_timer(s3_native_capture*,s3_parallel_pack*,s3_native_io,unsigned rate);
int s3_pp_step_timer(s3_parallel_pack*,unsigned worker,unsigned max_pairs,uint64_t bound,unsigned *processed);
#endif
#endif

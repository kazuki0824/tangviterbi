#include "s3_parallel_capture.h"
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#define HOT IRAM_ATTR
#else
#define HOT
#endif
static bool HOT healthy(void *ctx) {
 s3_parallel_pack*p=ctx;return !atomic_load_explicit(&p->fault,memory_order_relaxed);
}
static bool HOT available(void *ctx,unsigned bank) {return s3_pp_reclaim(ctx,bank)==S3_PP_OK;}
static bool HOT accept(void *ctx,unsigned bank,const uint32_t*words,unsigned first,unsigned count,
 uint64_t sample,uint64_t now,uint64_t deadline) {
 return s3_pp_accept(ctx,bank,words,first,count,sample,now,deadline)==S3_PP_OK;
}
bool s3_pp_native_start(s3_native_capture*s,s3_parallel_pack*p,s3_native_io io,unsigned rate) {
 if(!p || p->next_sample || p->count || p->reserved || p->submitted || p->have_carry)return false;
 s3_native_sink sink={p,healthy,available,available,accept};
 return s3_native_start_sink(s,sink,io,rate);
}

bool s3_pp_native_start_clocked(s3_native_capture*s,s3_parallel_pack*p,s3_native_io io,unsigned rate,
 s3_native_clock clock,void *clock_ctx,uint32_t clock_error) {
 if(!p || p->next_sample || p->count || p->reserved || p->submitted || p->have_carry)return false;
 s3_native_sink sink={p,healthy,available,available,accept};
 return s3_native_start_sink_clocked(s,sink,io,rate,clock,clock_ctx,clock_error);
}

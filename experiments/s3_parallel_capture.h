#ifndef S3_PARALLEL_CAPTURE_H
#define S3_PARALLEL_CAPTURE_H
#include "s3_native_capture.h"
#include "s3_parallel_pack.h"
/* Fresh initialized packer required. RF poll/collect/SPI lease scheduler share
 * one coordinator. Worker 0 can run there; worker 1 may run on the other core.
 * Caller supplies a common clock for worker deadlines, and polls/collects
 * often enough; this adapter alone is not a FreeRTOS scheduling proof.
 */
bool s3_pp_native_start(s3_native_capture*,s3_parallel_pack*,s3_native_io,unsigned rate);
/* Shared absolute epoch replaces the legacy coordinator-relative counter.
 * Give both workers exactly this clock/context; never read capture.now from
 * another core. Time quantization and callback WCET remain caller obligations.
 */
bool s3_pp_native_start_clocked(s3_native_capture*,s3_parallel_pack*,s3_native_io,
 unsigned rate,s3_native_clock,void *clock_ctx,uint32_t clock_error);
#endif

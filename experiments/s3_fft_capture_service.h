#ifndef S3_FFT_CAPTURE_SERVICE_H
#define S3_FFT_CAPTURE_SERVICE_H
#include "s3_native_capture.h"
/* Single core0 owner of the existing native capture + lossless TX ring.
 * max_words/slice_bound are caller WCET contracts, not measured bounds.
 * pump must return without blocking (e.g. DMA completion/credit step), retain
 * leased payload until its actual DMA completion, and stop on discontinuity.
 * It must not use PIE. Core1 does not touch capture, ring or DMA state.
 */
typedef struct {
    s3_native_capture *capture;
    unsigned max_words;
    uint32_t slice_bound;
    bool (*pump)(void *);
    void *pump_context;
} s3_fft_capture_service;
bool s3_fft_service_capture(void *,unsigned core);
#endif

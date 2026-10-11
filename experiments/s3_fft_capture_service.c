#include "s3_fft_capture_service.h"
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#define HOT IRAM_ATTR
#else
#define HOT
#endif
bool HOT s3_fft_service_capture(void *context,unsigned core)
{
    if(core==1)return true;
    s3_fft_capture_service *s=context;
    if(core||!s||!s->capture||!s->capture->bridge||!s->max_words||!s->slice_bound)
        return false;
    if(!s3_native_poll(s->capture))return false;
    unsigned taken;
    if(!s3_capture_step(s->capture->bridge,s->max_words,s->capture->now,
                        s->slice_bound,&taken)||
       (s->pump&&!s->pump(s->pump_context))) {
        s3_native_stop(s->capture);
        return false;
    }
    return s3_native_poll(s->capture);
}

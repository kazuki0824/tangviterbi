#include "s3_fft_simd_tiles.h"
#include <stddef.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#include "esp_memory_utils.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#define HOT IRAM_ATTR
static portMUX_TYPE contexts[2]={portMUX_INITIALIZER_UNLOCKED,portMUX_INITIALIZER_UNLOCKED};
#else
#define HOT
#endif
extern void s3_fft_simd_general(int16_t *,int16_t *,const int16_t *,unsigned);
extern void s3_fft_simd_pair(int16_t *,const int16_t *,unsigned);
extern void s3_fft_simd_final(int16_t *,const int16_t *,unsigned);
int HOT s3_fft_simd_tile(int16_t *data,const int16_t *table,unsigned stage,
                        unsigned start,unsigned count)
{
    uintptr_t d=(uintptr_t)data,t=(uintptr_t)table;
    if(!d||!t||((d|t)&15)||d>UINTPTR_MAX-32768||t>UINTPTR_MAX-16384||
       (d<t+16384&&t<d+32768)||stage>=13||!count||count>16||start>1024-count) return -1;
#ifdef ESP_PLATFORM
    if(!esp_ptr_internal(data)||!esp_ptr_internal(data+16383)||
       !esp_ptr_internal(table)||!esp_ptr_internal(table+8191))return -2;
    unsigned core=xPortGetCoreID();
    portENTER_CRITICAL(&contexts[core]);
#endif
    if(stage<11) {
        unsigned half=4096u>>stage;
        while(count) {
            unsigned butterfly=4*start,group=butterfly/half,offset=butterfly%half;
            unsigned amount=(half-offset)/4;
            if(amount>count)amount=count;
            unsigned a=group*2*half+offset;
            s3_fft_simd_general(data+2*a,data+2*(a+half),table+2*group,amount);
            count-=amount;start+=amount;
        }
    } else if(stage==11) s3_fft_simd_pair(data+16*start,table+4*start,count);
    else s3_fft_simd_final(data+16*start,table+8*start,count);
#ifdef ESP_PLATFORM
    portEXIT_CRITICAL(&contexts[core]);
#endif
    return 0;
}

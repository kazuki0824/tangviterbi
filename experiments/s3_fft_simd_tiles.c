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
int HOT s3_fft_simd_tile_n(int16_t *data,const int16_t *table,unsigned points,unsigned stage,
                          unsigned start,unsigned count)
{
    if(points!=2048&&points!=4096&&points!=8192)return -1;
    unsigned stages=points==2048?11:points==4096?12:13;
    uintptr_t data_bytes=4*points,table_bytes=2*points;
    uintptr_t d=(uintptr_t)data,t=(uintptr_t)table;
    if(!d||!t||((d|t)&15)||d>UINTPTR_MAX-data_bytes||t>UINTPTR_MAX-table_bytes||
       (d<t+table_bytes&&t<d+data_bytes)||stage>=stages||!count||count>16||start>points/8-count) return -1;
#ifdef ESP_PLATFORM
    if(!esp_ptr_internal(data)||!esp_ptr_internal(data+2*points-1)||
       !esp_ptr_internal(table)||!esp_ptr_internal(table+points-1))return -2;
    unsigned core=xPortGetCoreID();
    portENTER_CRITICAL(&contexts[core]);
#endif
    if(stage<stages-2) {
        unsigned half=(points/2)>>stage;
        while(count) {
            unsigned butterfly=4*start,group=butterfly/half,offset=butterfly%half;
            unsigned amount=(half-offset)/4;
            if(amount>count)amount=count;
            unsigned a=group*2*half+offset;
            s3_fft_simd_general(data+2*a,data+2*(a+half),table+2*group,amount);
            count-=amount;start+=amount;
        }
    } else if(stage==stages-2) s3_fft_simd_pair(data+16*start,table+4*start,count);
    else s3_fft_simd_final(data+16*start,table+8*start,count);
#ifdef ESP_PLATFORM
    portEXIT_CRITICAL(&contexts[core]);
#endif
    return 0;
}

int HOT s3_fft_simd_tile(int16_t *data,const int16_t *table,unsigned stage,
                        unsigned start,unsigned count)
{
    return s3_fft_simd_tile_n(data,table,8192,stage,start,count);
}

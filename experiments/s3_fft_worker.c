#include "s3_fft_worker.h"
#include "s3_fft_simd_tiles.h"
#include <limits.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#define HOT IRAM_ATTR
#else
#define HOT
#endif
/* IDF builds with -mdisable-hardware-atomics: ATOMIC_INT_LOCK_FREE may be 1
 * because read/modify/write needs an SDK fallback. This worker uses ONLY
 * aligned 32-bit loads/stores. Target evidence checks that those compile to
 * l32i/s32i + memw, with no external atomic helpers under the same flag.
 */
_Static_assert(sizeof(atomic_uint)==4&&_Alignof(atomic_uint)>=4,
               "worker requires naturally aligned 32-bit atomic storage");
_Static_assert(UINT_MAX==UINT32_MAX,"worker requires 32-bit unsigned");
enum { HALF_BLOCKS=512, END_PROGRESS=13*HALF_BLOCKS, TILE_BLOCKS=16 };
static int HOT actual_tile(void *ctx,int16_t *data,const int16_t *table,
                           unsigned stage,unsigned begin,unsigned count)
{
    (void)ctx;
    return s3_fft_simd_tile(data,table,stage,begin,count);
}
bool s3_fft_worker_init(s3_fft_worker *w,int16_t *data,const int16_t *table,
                        s3_fft_service_fn service,void *service_context,
                        s3_fft_tile_fn tile,void *tile_context)
{
    uintptr_t d=(uintptr_t)data,t=(uintptr_t)table;
    if(!w||!service||!d||!t||((d|t)&15)||d>UINTPTR_MAX-32768||
       t>UINTPTR_MAX-16384||(d<t+16384&&t<d+32768))return false;
    atomic_init(&w->progress[0],0);atomic_init(&w->progress[1],0);
    atomic_init(&w->fault,0);
    w->data=data;w->table=table;w->service=service;
    w->service_context=service_context;
    w->tile=tile?tile:actual_tile;w->tile_context=tile_context;
    return true;
}
static int HOT fail(s3_fft_worker *w)
{
    atomic_store_explicit(&w->fault,1,memory_order_release);
    return S3_FFT_WORKER_ERROR;
}
int HOT s3_fft_worker_step(s3_fft_worker *w,unsigned core)
{
    if(!w||core>1)return S3_FFT_WORKER_ERROR;
#ifdef ESP_PLATFORM
    if((unsigned)xPortGetCoreID()!=core)return fail(w);
#endif
    if(atomic_load_explicit(&w->fault,memory_order_acquire))return S3_FFT_WORKER_ERROR;
    if(!w->service(w->service_context,core))return fail(w);
    /* This core is the ONLY writer of its progress. Peer release publishes all
     * completed stage writes; acquire makes them visible before next stage.
     * Progress is monotone, so a peer already in the next stage also suffices.
     */
    unsigned p=atomic_load_explicit(&w->progress[core],memory_order_relaxed);
    int result;bool publish=false;
    if(p==END_PROGRESS)result=S3_FFT_WORKER_DONE;
    else if(p&&p%HALF_BLOCKS==0&&
            atomic_load_explicit(&w->progress[1-core],memory_order_acquire)<p)
        result=S3_FFT_WORKER_WAIT;
    else {
        if(atomic_load_explicit(&w->fault,memory_order_acquire))return S3_FFT_WORKER_ERROR;
        if(w->tile(w->tile_context,w->data,w->table,p/HALF_BLOCKS,
                   core*HALF_BLOCKS+p%HALF_BLOCKS,TILE_BLOCKS))return fail(w);
        publish=true;
        result=p+TILE_BLOCKS==END_PROGRESS?S3_FFT_WORKER_DONE:S3_FFT_WORKER_PROGRESS;
    }
    if(!w->service(w->service_context,core))return fail(w);
    if(atomic_load_explicit(&w->fault,memory_order_acquire))return S3_FFT_WORKER_ERROR;
    if(publish)atomic_store_explicit(&w->progress[core],p+TILE_BLOCKS,memory_order_release);
    return result;
}
bool HOT s3_fft_worker_ready(const s3_fft_worker *w)
{
    return w&&!atomic_load_explicit(&w->fault,memory_order_acquire)&&
        atomic_load_explicit(&w->progress[0],memory_order_acquire)==END_PROGRESS&&
        atomic_load_explicit(&w->progress[1],memory_order_acquire)==END_PROGRESS;
}

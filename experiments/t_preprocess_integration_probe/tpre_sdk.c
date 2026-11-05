#include "tpre_sdk.h"
#include "esp_attr.h"
#include "esp_memory_utils.h"
#include "esp_intr_alloc.h"
#include <string.h>

enum { SDK_CONFIG=20,SDK_CLOCK,SDK_WDT,SDK_RF,SDK_SPI };
static int IRAM_ATTR __attribute__((noinline)) sdk_fail(tpre_sdk *s,unsigned code) {
    atomic_store_explicit(&s->runtime->fault,code,memory_order_relaxed);
    tpre_request_stop(s->runtime);
    return TPRE_ERROR;
}
static bool internal_range(const void *p,size_t n) {
    uintptr_t a=(uintptr_t)p;
    return p&&n&&a<=UINTPTR_MAX-(n-1)&&esp_ptr_internal(p)&&esp_ptr_internal((const void *)(a+n-1));
}
bool tpre_sdk_init(tpre_sdk *s,tpre_runtime *r,const esp_task_wdt_config_t *wdt) {
    if(!s||!r||!wdt||!wdt->timeout_ms||(wdt->idle_core_mask&~3u)||
       !r->capture||r->capture->running||!r->pipeline||!r->native||s->initialized||
       r->io.ctx!=s||r->clock!=s3_cycle_clock_read||r->clock_ctx!=&s->clocks[0])return false;
    const void *objects[]={s,r,r->capture,r->pipeline,r->native};
    const size_t sizes[]={sizeof(*s),sizeof(*r),sizeof(*r->capture),sizeof(*r->pipeline),sizeof(*r->native)};
    for(unsigned i=0;i<5;i++)if(!internal_range(objects[i],sizes[i]))return false;
    for(unsigned i=0;i<TPRE_FRAMES;i++) {
        uint8_t *frame=r->frames[i].data;
        if(!internal_range(frame,TPRE_FRAME_BYTES)||((uintptr_t)frame&15u)||
           !esp_ptr_dma_capable(frame)||!esp_ptr_dma_capable(frame+TPRE_FRAME_BYTES-1))return false;
    }
    memset(s,0,sizeof(*s));s->runtime=r;s->watchdog=*wdt;s->epoch=r->epoch;s->initialized=true;
    for(unsigned i=0;i<2;i++){atomic_init(&s->ready[i],0);atomic_init(&s->stopped[i],0);}
    atomic_init(&s->run,0);return true;
}
bool tpre_sdk_open(tpre_sdk *s,const tpre_pins *p) {
    if(!s||!s->initialized||!p||s->open_attempted||s->attempted||s->runtime->capture->running)return false;
    s->open_attempted=true;
    spi_bus_config_t bus={.mosi_io_num=p->data0,.miso_io_num=p->data1,.sclk_io_num=p->clock,
        .quadwp_io_num=p->data2,.quadhd_io_num=p->data3,.data4_io_num=-1,.data5_io_num=-1,
        .data6_io_num=-1,.data7_io_num=-1,.max_transfer_sz=TPRE_FRAME_BYTES,
        .flags=SPICOMMON_BUSFLAG_MASTER|SPICOMMON_BUSFLAG_QUAD,
        .isr_cpu_id=ESP_INTR_CPU_AFFINITY_0,.intr_flags=ESP_INTR_FLAG_IRAM|ESP_INTR_FLAG_LEVEL1};
    if(spi_bus_initialize(SPI3_HOST,&bus,SPI_DMA_CH_AUTO)!=ESP_OK){s->poisoned=true;return false;}
    spi_device_interface_config_t dev={.command_bits=16,.address_bits=64,.clock_speed_hz=80000000,
        .mode=0,.spics_io_num=p->cs,.queue_size=TPRE_QUEUE_DEPTH,
        .flags=SPI_DEVICE_HALFDUPLEX|SPI_DEVICE_NO_DUMMY};
    if(spi_bus_add_device(SPI3_HOST,&dev,&s->device)!=ESP_OK){s->poisoned=true;return false;}
    int khz=0;
    if(spi_device_get_actual_freq(s->device,&khz)!=ESP_OK||khz!=80000){s->poisoned=true;return false;}
    return true;
}
int IRAM_ATTR tpre_sdk_submit(void *ctx,unsigned epoch,uint32_t sequence,const void *data,unsigned bytes) {
    tpre_sdk *s=ctx;
    if(s->poisoned||!s->device||epoch!=s->epoch||bytes!=TPRE_FRAME_BYTES||
       s->queued>=TPRE_QUEUE_DEPTH||sequence>UINT32_MAX/TPRE_FRAME_BYTES)return sdk_fail(s,SDK_SPI);
    unsigned slot=(s->head+s->queued)%TPRE_QUEUE_DEPTH;
    spi_transaction_t *t=&s->transactions[slot];
    *t=(spi_transaction_t){.flags=SPI_TRANS_MODE_QIO,.cmd=0xd711,
        .addr=((uint64_t)epoch<<32)|(sequence*TPRE_FRAME_BYTES),.length=bytes*8,.tx_buffer=data};
    s->sequence[slot]=sequence;++s->queued;
    if(spi_device_queue_trans(s->device,t,0)!=ESP_OK){s->poisoned=true;return sdk_fail(s,SDK_SPI);}
    return TPRE_OK;
}
int IRAM_ATTR tpre_sdk_reap(void *ctx,uint32_t *sequence) {
    tpre_sdk *s=ctx;
    if(s->poisoned||!s->device||!sequence)return sdk_fail(s,SDK_SPI);
    if(!s->queued)return TPRE_IDLE;
    spi_transaction_t *done=NULL;
    esp_err_t rc=spi_device_get_trans_result(s->device,&done,0);
    if(rc==ESP_ERR_TIMEOUT)return TPRE_IDLE;
    if(rc!=ESP_OK||done!=&s->transactions[s->head]){s->poisoned=true;return sdk_fail(s,SDK_SPI);}
    *sequence=s->sequence[s->head];s->head=(s->head+1)%TPRE_QUEUE_DEPTH;--s->queued;
    return TPRE_OK;
}
bool IRAM_ATTR tpre_sdk_feed(void *ctx,unsigned core) {
    tpre_sdk *s=ctx;
    uint64_t now=s3_cycle_clock_read(&s->clocks[core]);
    if(now==UINT64_MAX){sdk_fail(s,SDK_CLOCK);return false;}
    if(now>=s->next_feed[core]) {
        if(esp_task_wdt_reset()!=ESP_OK){sdk_fail(s,SDK_WDT);return false;}
        uint64_t interval=(uint64_t)s->watchdog.timeout_ms*240000/2;
        if(now>UINT64_MAX-interval){sdk_fail(s,SDK_CLOCK);return false;}
        s->next_feed[core]=now+interval;
    }
    return true;
}
tpre_io tpre_sdk_io(tpre_sdk *s) {return (tpre_io){s,tpre_sdk_submit,tpre_sdk_reap,tpre_sdk_feed};}
bool tpre_sdk_launch(tpre_sdk *s,StackType_t *const stacks[2],StaticTask_t *const tcbs[2],
                     unsigned bytes,const unsigned priority[2]) {
    if(!s||!s->initialized||!s->device||s->poisoned||s->attempted||!stacks||!tcbs||!priority||
       bytes<4096||bytes%sizeof(StackType_t)||stacks[0]==stacks[1]||tcbs[0]==tcbs[1]||
       tpre_stopping(s->runtime)||s->runtime->capture->running)return false;
    for(unsigned i=0;i<2;i++)if(!priority[i]||priority[i]>=configMAX_PRIORITIES||
        !internal_range(stacks[i],bytes)||!internal_range(tcbs[i],sizeof(*tcbs[i])))return false;
    s->attempted=true;
    for(unsigned i=0;i<2;i++)s->args[i]=(tpre_task_arg){s,i};
    s->handles[1]=xTaskCreateStaticPinnedToCore(tpre_sdk_task,"t-worker",bytes,&s->args[1],priority[1],stacks[1],tcbs[1],1);
    if(!s->handles[1]){sdk_fail(s,SDK_CONFIG);return false;}
    s->handles[0]=xTaskCreateStaticPinnedToCore(tpre_sdk_task,"t-owner",bytes,&s->args[0],priority[0],stacks[0],tcbs[0],0);
    if(!s->handles[0]){sdk_fail(s,SDK_CONFIG);return false;}
    return true;
}
void IRAM_ATTR tpre_sdk_task(void *argument) {
    tpre_task_arg *a=argument;tpre_sdk *s=a->sdk;unsigned core=a->core;
    tpre_runtime *r=s->runtime;bool subscribed=false,changed_idle=false;tpre_event event;
    if(tpre_stopping(r))goto finish;
    if(xPortGetCoreID()!=core||uxTaskPriorityGet(NULL)==0){sdk_fail(s,SDK_CONFIG);goto finish;}
    tpre_pie_warmup();
    if(!s3_cycle_clock_init(&s->clocks[core])||s->clocks[core].error>=r->step_bound){sdk_fail(s,SDK_CLOCK);goto finish;}
    esp_err_t status=esp_task_wdt_status(NULL);
    if(status!=ESP_OK&&(status!=ESP_ERR_NOT_FOUND||esp_task_wdt_add(NULL)!=ESP_OK)){sdk_fail(s,SDK_WDT);goto finish;}
    subscribed=true;
    if(!tpre_sdk_feed(s,core))goto finish;
    atomic_store_explicit(&s->ready[core],1,memory_order_release);
    while(!tpre_stopping(r)&&!atomic_load_explicit(&s->ready[1-core],memory_order_acquire)) {
        if(!tpre_sdk_feed(s,core))break;
        vTaskDelay(1);
    }
    if(tpre_stopping(r))goto finish;
    if(core==0) {
        while(!tpre_stopping(r)&&atomic_load_explicit(&s->ready[1],memory_order_acquire)<2) {
            if(!tpre_sdk_feed(s,0))break;
            vTaskDelay(1);
        }
        if(tpre_stopping(r))goto finish;
        if(!s3_cycle_clock_init(&s->clocks[0])||s->clocks[0].error>=r->step_bound){sdk_fail(s,SDK_CLOCK);goto finish;}
        r->clock_error=s->clocks[0].error;
        esp_task_wdt_config_t receiving=s->watchdog;receiving.idle_core_mask=0;
        if(esp_task_wdt_reconfigure(&receiving)!=ESP_OK){sdk_fail(s,SDK_WDT);goto finish;}
        changed_idle=true;
        if(tpre_stopping(r))goto finish;
        if(!s3_native_start_sink_clocked(r->capture,hbnative_sink(r->native),s3_native_mmio(),16,
            s3_cycle_clock_read,&s->clocks[0],r->clock_error)){sdk_fail(s,SDK_RF);goto finish;}
        atomic_store_explicit(&s->run,1,memory_order_release);
        while(!tpre_stopping(r)&&tpre_owner_step(r,&event)!=TPRE_ERROR){}
    } else {
        if(!s3_cycle_clock_init(&s->clocks[1])||s->clocks[1].error>=r->step_bound){sdk_fail(s,SDK_CLOCK);goto finish;}
        atomic_store_explicit(&s->ready[1],2,memory_order_release);
        while(!tpre_stopping(r)&&!atomic_load_explicit(&s->run,memory_order_acquire)) {
            if(!tpre_sdk_feed(s,1))break;
        }
        while(!tpre_stopping(r)&&tpre_worker_step(r,&event)!=TPRE_ERROR){}
    }
finish:
    tpre_request_stop(r);
    if(core==0) {
        s3_native_stop(r->capture);
        while(!atomic_load_explicit(&s->stopped[1],memory_order_acquire)) {
            if(subscribed)tpre_sdk_feed(s,0);
            vTaskDelay(1);
        }
        for(unsigned i=0;i<TPRE_QUEUE_DEPTH&&s->queued;i++) {
            uint32_t sequence;
            if(tpre_sdk_reap(s,&sequence)!=TPRE_OK)break;
        }
        if(changed_idle&&esp_task_wdt_reconfigure(&s->watchdog)!=ESP_OK)sdk_fail(s,SDK_WDT);
    }
    if(subscribed&&esp_task_wdt_delete(NULL)!=ESP_OK)sdk_fail(s,SDK_WDT);
    atomic_store_explicit(&s->stopped[core],1,memory_order_release);
    vTaskDelete(NULL);
}

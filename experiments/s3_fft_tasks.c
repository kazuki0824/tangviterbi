#include "s3_fft_tasks.h"
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#include "esp_memory_utils.h"
#include <string.h>
enum { IDLE=0,RUN=1,STOP=2 };
static void peer_task(void *arg)
{
 s3_fft_tasks *s=arg;
 for(;;) {
  ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
  unsigned cmd=atomic_load_explicit(&s->command,memory_order_acquire);
  if(cmd==STOP) {atomic_store_explicit(&s->ack,STOP,memory_order_release);vTaskSuspend(NULL);}
  if(cmd!=RUN)continue;
  while(atomic_load_explicit(&s->command,memory_order_acquire)==RUN) {
   int rc=s3_fft_worker_step(&s->worker,1);
   if(rc==S3_FFT_WORKER_ERROR||rc==S3_FFT_WORKER_DONE)break;
   /* WAIT returns with interrupts enabled. Yield only at barriers, not
    * between every tile; the target wait/service costs remain measurable. */
   if(rc==S3_FFT_WORKER_WAIT)taskYIELD();
  }
  atomic_store_explicit(&s->ack,IDLE,memory_order_release);
 }
}
bool s3_fft_tasks_open(s3_fft_tasks *s,StackType_t *stack,unsigned bytes)
{
 if(!s||!stack||bytes<2048||(bytes%16)||((uintptr_t)stack&15)||!esp_ptr_internal(s)||xPortGetCoreID()!=0||
    !esp_ptr_internal(stack)||!esp_ptr_internal((uint8_t*)stack+bytes-1))return false;
 memset(s,0,sizeof(*s));s->stack=stack;s->stack_bytes=bytes;
 atomic_init(&s->command,IDLE);atomic_init(&s->ack,IDLE);
 s->peer=xTaskCreateStaticPinnedToCore(peer_task,"T_FFT",bytes,s,5,stack,&s->tcb,1);
 return s->peer!=NULL;
}
bool s3_fft_tasks_begin(s3_fft_tasks *s,int16_t *data,const int16_t *table,unsigned points,
                       s3_fft_service_fn service,void *context)
{
 if(!s||!s->peer||s->active||xPortGetCoreID()!=0||
    atomic_load_explicit(&s->command,memory_order_acquire)!=IDLE||
    atomic_load_explicit(&s->ack,memory_order_acquire)!=IDLE)return false;
 if(!s3_fft_worker_init_n(&s->worker,data,table,points,service,context,NULL,NULL))return false;
 s->active=true;
 atomic_store_explicit(&s->ack,RUN,memory_order_relaxed);
 atomic_store_explicit(&s->command,RUN,memory_order_release);
 xTaskNotifyGive(s->peer);return true;
}
int IRAM_ATTR s3_fft_tasks_owner_step(s3_fft_tasks *s)
{
 if(!s||!s->active||xPortGetCoreID()!=0)return S3_FFT_WORKER_ERROR;
 int rc=s3_fft_worker_step(&s->worker,0);
 if(rc==S3_FFT_WORKER_ERROR) {
  atomic_store_explicit(&s->command,IDLE,memory_order_release);
  return rc; /* caller stops RF and joins peer before reusing a frame */
 }
 if(!s3_fft_worker_ready(&s->worker)||
    atomic_load_explicit(&s->ack,memory_order_acquire)!=IDLE)return S3_FFT_WORKER_PROGRESS;
 atomic_store_explicit(&s->command,IDLE,memory_order_release);s->active=false;
 return S3_FFT_WORKER_DONE;
}
bool s3_fft_tasks_stop(s3_fft_tasks *s,TickType_t timeout)
{
 if(!s||!s->peer||xPortGetCoreID()!=0)return false;
 /* Only use after capture/transport have stopped. A stuck task may not be
  * deleted and its stack reused while it could still touch a frame. */
 atomic_store_explicit(&s->command,STOP,memory_order_release);xTaskNotifyGive(s->peer);
 TickType_t begin=xTaskGetTickCount();
 while(atomic_load_explicit(&s->ack,memory_order_acquire)!=STOP||eTaskGetState(s->peer)!=eSuspended) {
  if((TickType_t)(xTaskGetTickCount()-begin)>=timeout)return false;
  vTaskDelay(1);
 }
 vTaskDelete(s->peer);s->peer=NULL;s->active=false;return true;
}
#endif

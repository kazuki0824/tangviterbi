#include "s3_raw_tasks.h"
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
enum { RAW_TASK_CONFIG=1,RAW_TASK_CLOCK,RAW_TASK_WDT,RAW_TASK_RF,RAW_TASK_PACK,RAW_TASK_SPI };
static void IRAM_ATTR fault(s3_raw_tasks*r,unsigned code) {
 atomic_store_explicit(&r->fault,code,memory_order_relaxed);
 atomic_store_explicit(&r->stop,1,memory_order_release);
}
void s3_raw_tasks_request_stop(s3_raw_tasks*r) {
 if(r)atomic_store_explicit(&r->stop,1,memory_order_release);
}
static bool IRAM_ATTR stopping(s3_raw_tasks*r) {
 return atomic_load_explicit(&r->stop,memory_order_acquire)!=0;
}
bool s3_raw_tasks_init(s3_raw_tasks*r,const s3_raw_tasks_config*c) {
 if(!r||!c||!c->pack||!c->capture||c->capture->running||
    (c->rate!=16&&c->rate!=40)||!c->epoch||c->epoch>UINT16_MAX||
    !c->slice_pairs||c->slice_pairs>S3_PP_WORDS/2||
    !c->slice_bound[0]||!c->slice_bound[1]||!c->watchdog.timeout_ms||
    (c->watchdog.idle_core_mask&~3u))return false;
 for(unsigned i=0;i<2;++i)
  if(!c->ports[i]||!c->transfers[i]||c->transfers[i]->active||
     !c->ports[i]->bulk||c->ports[i]->busy||c->ports[i]->poisoned)return false;
 if(c->ports[0]==c->ports[1]||c->transfers[0]==c->transfers[1])return false;
 if(c->pack->count||c->pack->reserved||c->pack->next_sample||
    atomic_load_explicit(&c->pack->fault,memory_order_relaxed))return false;
 memset(r,0,sizeof(*r));r->config=*c;
 atomic_init(&r->run,0);atomic_init(&r->stop,0);atomic_init(&r->fault,0);
 for(unsigned i=0;i<2;++i){atomic_init(&r->ready[i],0);atomic_init(&r->stopped[i],0);}
 return true;
}
static bool IRAM_ATTR feed(s3_raw_tasks*r,unsigned core,bool force) {
 uint64_t now=s3_cycle_clock_read(&r->clocks[core]);
 if(now==UINT64_MAX){fault(r,RAW_TASK_CLOCK);return false;}
 if(force||now>=r->next_feed[core]) {
  if(esp_task_wdt_reset()!=ESP_OK){fault(r,RAW_TASK_WDT);return false;}
  uint64_t interval=(uint64_t)r->config.watchdog.timeout_ms*240000/2;
  if(now>UINT64_MAX-interval){fault(r,RAW_TASK_CLOCK);return false;}
  r->next_feed[core]=now+interval;
 }
 return true;
}
static bool IRAM_ATTR poll_rf(s3_raw_tasks*r) {
 if(stopping(r))return false;
 if(!s3_native_poll(r->config.capture)){fault(r,RAW_TASK_RF);return false;}
 return true;
}
static bool IRAM_ATTR pack_slice(s3_raw_tasks*r,unsigned core) {
 unsigned n;
 int rc=s3_pp_step_clocked_quantized(r->config.pack,core,r->config.slice_pairs,
    s3_cycle_clock_read,&r->clocks[core],r->clocks[core].error,
    r->config.slice_bound[core],&n);
 if(rc!=S3_PP_OK&&rc!=S3_PP_EMPTY){fault(r,RAW_TASK_PACK);return false;}
 return true;
}
static bool IRAM_ATTR owner_iteration(s3_raw_tasks*r) {
 if(!poll_rf(r)||!pack_slice(r,0)||!poll_rf(r))return false;
 uint64_t now=s3_cycle_clock_read(&r->clocks[0]);
 if(now==UINT64_MAX){fault(r,RAW_TASK_CLOCK);return false;}
 if(s3_pp_collect(r->config.pack,now)!=S3_PP_OK){fault(r,RAW_TASK_PACK);return false;}
 if(!poll_rf(r))return false;
 for(unsigned i=0;i<2;++i) {
  s3_pp_transfer*x=r->config.transfers[i];
  if(x->active) {
   esp_err_t rc=s3_pp_spi_reap(x);
   if(rc!=ESP_OK&&rc!=ESP_ERR_TIMEOUT){fault(r,RAW_TASK_SPI);return false;}
  }
  if(!poll_rf(r))return false;
  if(!x->active) {
   esp_err_t rc=s3_pp_spi_submit(x,r->config.pack,r->config.ports[i],r->config.epoch);
   if(rc!=ESP_OK&&rc!=ESP_ERR_NOT_FINISHED){fault(r,RAW_TASK_SPI);return false;}
  }
  if(!poll_rf(r))return false;
 }
 return feed(r,0,false);
}
void IRAM_ATTR s3_raw_task_entry(void*argument) {
 s3_raw_task_arg*a=argument;
 if(!a||!a->runtime||a->core>1){vTaskDelete(NULL);return;}
 s3_raw_tasks*r=a->runtime;unsigned core=a->core;
 bool subscribed=false,changed_idle=false;
 if(stopping(r))goto finish;
 if(xPortGetCoreID()!=core||uxTaskPriorityGet(NULL)==0){fault(r,RAW_TASK_CONFIG);goto finish;}
 if(!s3_cycle_clock_init(&r->clocks[core])||r->clocks[core].error>=r->config.slice_bound[core]) {
  fault(r,RAW_TASK_CLOCK);goto finish;
 }
 // This entry owns the entire dedicated task lifetime. Its subscription,
 // including one supplied by the creator, must end before task deletion.
 esp_err_t status=esp_task_wdt_status(NULL);
 if(status!=ESP_OK&&(status!=ESP_ERR_NOT_FOUND||esp_task_wdt_add(NULL)!=ESP_OK)) {
  fault(r,RAW_TASK_WDT);goto finish;
 }
 subscribed=true;
 if(!feed(r,core,true))goto finish;
 atomic_store_explicit(&r->ready[core],1,memory_order_release);
 while(!stopping(r)&&!atomic_load_explicit(&r->ready[1-core],memory_order_acquire)) {
  if(!feed(r,core,true))break;
  vTaskDelay(1); // RF is OFF: no tick-sized sleep in the receiving loop.
 }
 if(stopping(r))goto finish;
 if(core==0) {
  // Peer must acknowledge it has left every tick-sleeping startup wait.
  while(!stopping(r)&&atomic_load_explicit(&r->ready[1],memory_order_acquire)<2) {
   if(!feed(r,core,true))break;
   vTaskDelay(1);
  }
  if(stopping(r))goto finish;
  // Startup may have let idle run. Calibrate again only after the peer has
  // entered its permanently awake gate; no idle/WAITI behavior is assumed.
  if(!s3_cycle_clock_init(&r->clocks[0])||r->clocks[0].error>=r->config.slice_bound[0]) {
   fault(r,RAW_TASK_CLOCK);goto finish;
  }
  if(!feed(r,0,true))goto finish;
  esp_task_wdt_config_t receive=r->config.watchdog;receive.idle_core_mask=0;
  if(esp_task_wdt_reconfigure(&receive)!=ESP_OK){fault(r,RAW_TASK_WDT);goto finish;}
  changed_idle=true;
  if(stopping(r))goto finish;
  if(!s3_pp_native_start_clocked(r->config.capture,r->config.pack,r->config.io,
     r->config.rate,s3_cycle_clock_read,&r->clocks[0],r->clocks[0].error)) {
   fault(r,RAW_TASK_RF);goto finish;
  }
  atomic_store_explicit(&r->run,1,memory_order_release);
  while(!stopping(r)&&owner_iteration(r)){}
 } else {
  if(!s3_cycle_clock_init(&r->clocks[1])||r->clocks[1].error>=r->config.slice_bound[1]) {
   fault(r,RAW_TASK_CLOCK);goto finish;
  }
  if(!feed(r,1,true))goto finish;
  atomic_store_explicit(&r->ready[1],2,memory_order_release);
  while(!stopping(r)&&!atomic_load_explicit(&r->run,memory_order_acquire)) {
   if(!feed(r,core,false))break;
   // No tick sleep after the ready=2 acknowledgement: RF may start now.
  }
  while(!stopping(r)&&pack_slice(r,1)&&feed(r,1,false)){}
 }
finish:
 s3_raw_tasks_request_stop(r);
 if(core==0) {
  s3_native_stop(r->config.capture);
  // Never reuse payload while a peer can still access it. A stalled peer
  // remains watched; do not invent a timeout that makes reuse safe.
  while(!atomic_load_explicit(&r->stopped[1],memory_order_acquire)) {
   if(subscribed)feed(r,0,true);
   vTaskDelay(1);
  }
  for(unsigned i=0;i<2;++i)if(r->config.transfers[i]->active) {
   esp_err_t rc=s3_pp_spi_reap(r->config.transfers[i]);
   if(rc!=ESP_OK&&rc!=ESP_ERR_TIMEOUT)fault(r,RAW_TASK_SPI);
   // TIMEOUT retains the DMA lease; supervisor must drain/reset before reuse.
  }
  if(changed_idle&&esp_task_wdt_reconfigure(&r->config.watchdog)!=ESP_OK)fault(r,RAW_TASK_WDT);
 }
 if(subscribed&&esp_task_wdt_delete(NULL)!=ESP_OK)fault(r,RAW_TASK_WDT);
 atomic_store_explicit(&r->stopped[core],1,memory_order_release);
 vTaskDelete(NULL);
}
#endif

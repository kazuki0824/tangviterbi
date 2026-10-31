/* Lifecycle test: actual task integration with SDK/RF/packing/SPI callees
 * mocked. Does NOT test real RF, DSP timing, DMA or SDK lock behavior. */
#include "s3_raw_tasks.h"
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <stdatomic.h>
static s3_raw_tasks r;
static s3_parallel_pack pack;
static s3_native_capture capture;
static s3_spi_port ports[2];static s3_pp_transfer transfers[2];
static _Thread_local unsigned core;
static unsigned mode;
static atomic_uint subscribed[2],feed_count[2],idle_mask,rf_started,rf_stopped;
static atomic_uint deletes,delayed_peer,release_peer;
static unsigned polls,reconfigs,reaps,submits;
unsigned xPortGetCoreID(void){return core;}
unsigned uxTaskPriorityGet(TaskHandle_t h){assert(!h);return mode==8?0:1;}
void vTaskDelete(TaskHandle_t h){assert(!h);atomic_fetch_add(&deletes,1);}
void vTaskDelay(TickType_t n){
 assert(n==1);
 // During receive neither task is allowed to sleep a whole tick.
 assert(!atomic_load(&rf_started)||atomic_load(&rf_stopped));
 if(core==1&&mode==1&&!atomic_exchange(&delayed_peer,1))
  while(!atomic_load(&release_peer))sched_yield();
 sched_yield();
}
esp_err_t esp_task_wdt_status(TaskHandle_t h){assert(!h);return atomic_load(&subscribed[core])?ESP_OK:ESP_ERR_NOT_FOUND;}
esp_err_t esp_task_wdt_add(TaskHandle_t h){assert(!h);if(mode==2&&core==1)return ESP_ERR_INVALID_STATE;atomic_store(&subscribed[core],1);return ESP_OK;}
esp_err_t esp_task_wdt_delete(TaskHandle_t h){assert(!h);assert(atomic_exchange(&subscribed[core],0));return ESP_OK;}
esp_err_t esp_task_wdt_reset(void){assert(atomic_load(&subscribed[core]));atomic_fetch_add(&feed_count[core],1);return ESP_OK;}
esp_err_t esp_task_wdt_reconfigure(const esp_task_wdt_config_t*c){
 assert(core==0&&c->timeout_ms==5000&&c->trigger_panic);++reconfigs;
 if(!c->idle_core_mask)assert(atomic_load(&subscribed[0])&&atomic_load(&subscribed[1]));
 else assert(c->idle_core_mask==3&&atomic_load(&rf_stopped));
 atomic_store(&idle_mask,c->idle_core_mask);return ESP_OK;
}
bool s3_cycle_clock_init(s3_cycle_clock_state*s){
 assert(s==&r.clocks[core]);*s=(s3_cycle_clock_state){100000,0,core?431:313,true};return mode!=3||core!=1;
}
uint64_t s3_cycle_clock_read(void*ctx){assert(ctx==&r.clocks[core]);s3_cycle_clock_state*s=ctx;return s->upper+=100;}
bool s3_pp_native_start_clocked(s3_native_capture*s,s3_parallel_pack*p,s3_native_io io,unsigned rate,s3_native_clock clock,void*ctx,uint32_t error){
 (void)io;assert(core==0&&s==&capture&&p==&pack&&rate==40&&clock==s3_cycle_clock_read&&ctx==&r.clocks[0]&&error==313);
 assert(atomic_load(&r.ready[1])==2&&atomic_load(&idle_mask)==0);
 s->running=true;atomic_store(&rf_started,1);return true;
}
void s3_native_stop(s3_native_capture*s){assert(core==0&&s==&capture);s->running=false;atomic_store(&rf_stopped,1);}
bool s3_native_poll_budget(s3_native_capture*s,unsigned *budget){
 assert(*budget==(polls%7==0?1024u:0u));*budget=0;
 assert(core==0&&s==&capture&&s->running);if(++polls==100)s3_raw_tasks_request_stop(&r);return true;
}
int s3_pp_step_clocked_quantized(s3_parallel_pack*p,unsigned worker,unsigned max_pairs,s3_pp_clock clock,void*ctx,uint32_t error,uint64_t bound,unsigned*processed){
 assert(p==&pack&&worker==core&&max_pairs==512&&ctx==&r.clocks[core]&&error==r.clocks[core].error&&bound==10000);
 assert(atomic_load(&rf_started));clock(ctx);clock(ctx);*processed=1;return S3_PP_OK;
}
int s3_pp_collect(s3_parallel_pack*p,uint64_t now){assert(core==0&&p==&pack&&now>=100000);return S3_PP_OK;}
esp_err_t s3_pp_spi_reap(s3_pp_transfer*x){assert(core==0&&x->active);++reaps;if(mode==4)return ESP_ERR_TIMEOUT;x->active=false;return ESP_OK;}
esp_err_t s3_pp_spi_submit(s3_pp_transfer*x,s3_parallel_pack*p,s3_spi_port*port,unsigned epoch){
 assert(core==0&&p==&pack&&epoch==1&&port->bulk&&!x->active);++submits;x->active=true;
 return mode==4?ESP_ERR_INVALID_STATE:ESP_OK;
}
static void*entry(void*a){core=((s3_raw_task_arg*)a)->core;s3_raw_task_entry(a);return NULL;}
struct host_task {pthread_t thread;};
static struct host_task created[2];
static unsigned create_calls;
TaskHandle_t xTaskCreateStaticPinnedToCore(void (*fn)(void*),const char*name,unsigned bytes,
 void*arg,unsigned priority,StackType_t*stack,StaticTask_t*tcb,int target){
 assert(fn==s3_raw_task_entry&&name&&bytes==4096&&priority==1&&stack&&tcb);
 assert(target==(create_calls==0?1:0));++create_calls;
 assert(((s3_raw_task_arg*)arg)->core==(unsigned)target);
 if((mode==10&&target==1)||(mode==11&&target==0))return NULL;
 assert(!pthread_create(&created[target].thread,NULL,entry,arg));return &created[target];
}
static void reset(unsigned m){
 mode=m;polls=reconfigs=reaps=submits=0;memset(&pack,0,sizeof(pack));memset(&capture,0,sizeof(capture));memset(ports,0,sizeof(ports));memset(transfers,0,sizeof(transfers));
 for(unsigned i=0;i<2;++i){ports[i].bulk=true;atomic_store(&subscribed[i],m==9);atomic_store(&feed_count[i],0);}
 atomic_store(&idle_mask,3);atomic_store(&rf_started,0);atomic_store(&rf_stopped,0);atomic_store(&deletes,0);atomic_store(&delayed_peer,0);atomic_store(&release_peer,0);
 s3_raw_tasks_config c={.pack=&pack,.capture=&capture,.ports={&ports[0],&ports[1]},.transfers={&transfers[0],&transfers[1]},.rate=40,.epoch=1,.slice_pairs=512,.slice_bound={10000,10000},.watchdog={5000,3,true}};
 if(m==6)c.slice_bound[1]=100;
 assert(s3_raw_tasks_init(&r,&c));
 if(m==5)s3_raw_tasks_request_stop(&r);
}
int main(void){
 for(unsigned m=0;m<10;++m){
  if(m==7)continue;
  reset(m);s3_raw_task_arg args[2]={{&r,0},{&r,1}};pthread_t threads[2];
  if(m==1){
   // Hold peer in its last sleeping startup wait while core0 becomes ready.
   assert(!pthread_create(&threads[1],NULL,entry,&args[1]));
   while(!atomic_load(&delayed_peer))sched_yield();
   assert(!pthread_create(&threads[0],NULL,entry,&args[0]));
   while(!atomic_load(&r.ready[0]))sched_yield();
   assert(!atomic_load(&rf_started));atomic_store(&release_peer,1);
  }else{
   assert(!pthread_create(&threads[0],NULL,entry,&args[0]));assert(!pthread_create(&threads[1],NULL,entry,&args[1]));
  }
  for(unsigned i=0;i<2;++i)assert(!pthread_join(threads[i],NULL));
  assert(atomic_load(&deletes)==2&&atomic_load(&r.stopped[0])&&atomic_load(&r.stopped[1]));
  assert(atomic_load(&idle_mask)==3&&!atomic_load(&subscribed[0])&&!atomic_load(&subscribed[1]));
  if(m==2||m==3||m==5||m==6||m==8){assert(!atomic_load(&rf_started)&&!reconfigs);if(m!=5)assert(atomic_load(&r.fault));}
  else assert(atomic_load(&rf_started)&&atomic_load(&rf_stopped)&&reconfigs==2&&submits);
  if(m==4)assert(atomic_load(&r.fault)&&transfers[0].active); // no false DMA release
  else if(m<2||m==9)assert(!atomic_load(&r.fault)&&!transfers[0].active&&!transfers[1].active);
 }
 puts("PASS actual task lifecycle: startup sleeping-peer race, calibration/WDT failure, owner calls, stop/join, watchdog restoration, retained failed DMA lease; pre-cancel, calibration-bound rejection, idle-priority rejection, pre-existing subscription cleanup");
 for(unsigned m=10;m<=12;++m){
  reset(m);create_calls=0;s3_raw_launch launch={0};
  StackType_t storage[2][4096/sizeof(StackType_t)];StaticTask_t tcbs[2];
  StackType_t*stacks[2]={storage[0],storage[1]};StaticTask_t*controls[2]={&tcbs[0],&tcbs[1]};
  unsigned priorities[2]={0,1};
  assert(!s3_raw_tasks_launch(&r,&launch,stacks,controls,4096,priorities));
  assert(!create_calls&&!launch.attempted);priorities[0]=configMAX_PRIORITIES;
  assert(!s3_raw_tasks_launch(&r,&launch,stacks,controls,4096,priorities));
  assert(!create_calls&&!launch.attempted);priorities[0]=1;
  assert(s3_raw_tasks_launch(&r,&launch,stacks,controls,4096,priorities)==(m==12));
  unsigned calls=create_calls;
  assert(!s3_raw_tasks_launch(&r,&launch,stacks,controls,4096,priorities));
  assert(create_calls==calls); // Never duplicate a partial or completed launch.
  for(unsigned i=0;i<2;++i)if(launch.handles[i])assert(!pthread_join(created[i].thread,NULL));
  assert(create_calls==(m==10?1:2));
  assert(atomic_load(&deletes)==(m==10?0:m==11?1:2));
  assert(atomic_load(&idle_mask)==3&&!atomic_load(&subscribed[0])&&!atomic_load(&subscribed[1]));
  if(m!=12){
   assert(!atomic_load(&rf_started)&&!reconfigs&&atomic_load(&r.stop)&&atomic_load(&r.fault));
   assert(!launch.handles[0]&&!atomic_load(&r.stopped[0]));
   assert(atomic_load(&r.stopped[1])==(m==11));
  }else assert(atomic_load(&rf_started)&&atomic_load(&rf_stopped)&&!atomic_load(&r.fault));
 }
 puts("PASS actual static launcher: peer-first, first/second creation failure, partial cleanup, successful launch, priority validation and duplicate rejection");
}

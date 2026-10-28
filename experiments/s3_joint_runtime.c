/* Executed with generated copies of native/packing C and verbatim owner body.
 * Virtual cost experiment; no host timing is interpreted as ESP32 timing. */
#define _XOPEN_SOURCE 700
#include "s3_parallel_capture.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ucontext.h>
#include <limits.h>
#include "joint_costs.h"
enum {CTRL=0x60033d5c,INDEX=0x60033d60,SELECT=0x600c101c};
static uint32_t banks[3][16384];
static _Alignas(16) uint8_t payload[4][32768];
static s3_parallel_pack pack;
static s3_native_capture capture;
static uint64_t now,ready[2],samples,phase,limit,wire_done[2],irq_at[2],next_tick;
static unsigned mask,index_rf,cpp,core,rf_on,started,stopped[2],share,slice,irq_cycles,stall_percent;
static ucontext_t scheduler,contexts[2];static char stacks[2][262144];
static uint64_t charged[2][CATEGORIES],counts[2][CATEGORIES],interrupts[2],stall[2];
static uint64_t iterations[2],polls,last_poll,max_poll_gap,max_owner_gap,peak_bytes,checked_bytes;
static uint64_t min_deadline=UINT64_MAX,transfers_done[2],last_submit[2],max_submit_gap[2];
static uint64_t accepted[3],max_publish_latency;
static unsigned outcome,prepare_per_iteration,prepare_per_poll,accept_reject_reason;
static uint64_t attempted_arena_bytes;
void joint_accept_reject(unsigned reason,uint64_t bytes){accept_reject_reason=reason;attempted_arena_bytes=bytes;}
static unsigned failure_written,failure_prepared,failure_prepare_done;
static uint64_t max_wire_to_reap[2],failed_admission_remaining,max_sampled_pack[2];
void joint_failed_admission(uint64_t d,uint64_t t){failed_admission_remaining=d>t?d-t:0;}
void joint_pack_interval(uint64_t n){if(n>max_sampled_pack[core])max_sampled_pack[core]=n;}
static void advance(uint64_t t) {
 assert(t>=now);
 if(rf_on){phase+=t-now;while(phase>=cpp){phase-=cpp;
  for(unsigned b=0;b<3;b++)if(mask&(1u<<b))banks[b][index_rf]=(uint32_t)samples&0xfffff;
  ++samples;index_rf=(index_rf+1)&16383;
 }}now=t;
}
void joint_charge(unsigned category,uint64_t cycles) {
 assert(category<CATEGORIES&&cycles);
 if(!started)return; // RF-off lifecycle is outside this receiving experiment.
 charged[core][category]+=cycles;counts[core][category]++;
 uint64_t extra=(cycles*stall_percent+99)/100;stall[core]+=extra;
 ready[core]=now+cycles+extra;
 swapcontext(&contexts[core],&scheduler);
}
uint64_t joint_now(void*ctx){(void)ctx;return now;}
static uint32_t rd(void*c,uint32_t a){(void)c;return a==INDEX?index_rf:a==SELECT?mask:0;}
static void wr(void*c,uint32_t a,uint32_t v){(void)c;if(a==CTRL)rf_on=v>>31;if(a==SELECT)mask=v&15;}
static uint32_t*bank(void*c,unsigned n){(void)c;return banks[n];}
static uint8_t expected(uint64_t at){uint64_t a=((at/5)*2)&0xfffff,b=(a+1)&0xfffff;return (a|(b<<20))>>((at%5)*8);}
static void check_payload(uint64_t seq,const uint8_t*data){
 for(unsigned i=0;i<S3_PP_TX_BYTES;i++){
  /* Native startup intentionally starts sample 0 in this ideal RF model. */
  if(data[i]!=expected(seq*S3_PP_TX_BYTES+i)){outcome=90;return;}
 }checked_bytes+=S3_PP_TX_BYTES;
}
/* Minimal ABI used by the verbatim owner function; SDK calls are costed models. */
typedef int esp_err_t;
enum {ESP_OK,ESP_ERR_TIMEOUT,ESP_ERR_NOT_FINISHED};
typedef struct {unsigned host;} s3_spi_port;
typedef struct {bool active;uint64_t sequence;const uint8_t*data;unsigned host;} s3_pp_transfer;
typedef struct {unsigned timeout_ms;} watchdog_config;
typedef struct {
 struct {s3_native_capture*capture;s3_parallel_pack*pack;unsigned slice_pairs,epoch;
 uint64_t slice_bound[2];s3_pp_transfer*transfers[2];s3_spi_port*ports[2];watchdog_config watchdog;} config;
 unsigned clocks[2];uint64_t next_feed[2];unsigned stop,fault;
} s3_raw_tasks;
static s3_raw_tasks runtime;
static s3_spi_port ports[2]={{0},{1}};static s3_pp_transfer tx[2];
#define IRAM_ATTR
#define S3_RAW_PREPARE_WORDS_PER_ITERATION prepare_per_iteration
#define RAW_TASK_RF 1
#define RAW_TASK_PACK 2
#define RAW_TASK_SPI 3
#define RAW_TASK_CLOCK 4
static bool stopping(s3_raw_tasks*r){return r->stop||outcome;}
static void fault(s3_raw_tasks*r,unsigned code){r->fault=code;r->stop=1;}
static uint64_t s3_cycle_clock_read(void*x){return joint_now(x);}
static bool feed(s3_raw_tasks*r,unsigned c,bool force){
 if(force||now>=r->next_feed[c]){joint_charge(WDT,COST_WDT);r->next_feed[c]=now+600000000;}return true;
}
static bool poll_rf(s3_raw_tasks*r,unsigned*budget){
 if(stopping(r))return false;
 if(last_poll&&now-last_poll>max_poll_gap)max_poll_gap=now-last_poll;last_poll=now;++polls;
 unsigned available=*budget<prepare_per_poll?*budget:prepare_per_poll;
 unsigned local=available;bool ok=s3_native_poll_budget(r->config.capture,&local);*budget-=available-local;
 if(!ok){failure_written=(index_rf-capture.expected)&16383;failure_prepared=capture.prepared;failure_prepare_done=capture.prepare_done;fault(r,RAW_TASK_RF);return false;}return true;
}
static bool pack_slice(s3_raw_tasks*r,unsigned c){
 unsigned n;int rc=s3_pp_step_clocked_quantized(&pack,c,slice,joint_now,0,0,r->config.slice_bound[c],&n);
 if(rc!=S3_PP_OK&&rc!=S3_PP_EMPTY){fault(r,RAW_TASK_PACK);return false;}return true;
}
static esp_err_t s3_pp_spi_reap(s3_pp_transfer*x){
 unsigned h=x->host;
 if(now<wire_done[h]){joint_charge(REAP_RUNNING,h?44:42);return ESP_ERR_TIMEOUT;}
 joint_charge(REAP_DONE,COST_REAP_DONE);
 if(now-wire_done[h]>max_wire_to_reap[h])max_wire_to_reap[h]=now-wire_done[h];
 check_payload(x->sequence,x->data);
 assert(s3_pp_complete(&pack,x->sequence)==S3_PP_OK);
 ++transfers_done[h];x->active=false;return ESP_OK;
}
static esp_err_t s3_pp_spi_submit(s3_pp_transfer*x,s3_parallel_pack*p,s3_spi_port*port,unsigned epoch){
 (void)epoch;unsigned h=port->host;uint64_t seq;const uint8_t*data;
 if(p->submitted>=p->published/S3_PP_TX_BYTES){joint_charge(SUBMIT_EMPTY,COST_SUBMIT_EMPTY);return ESP_ERR_NOT_FINISHED;}
 joint_charge(SUBMIT_DONE,COST_SUBMIT_DONE);
 assert(s3_pp_take(p,&seq,&data)==S3_PP_OK);x->sequence=seq;x->data=data;x->host=h;x->active=true;
 uint64_t wire=((uint64_t)S3_PP_TX_BYTES*8+80)*3/(h?4:8);
 wire_done[h]=now+wire;irq_at[h]=wire_done[h];
 if(last_submit[h]&&now-last_submit[h]>max_submit_gap[h])max_submit_gap[h]=now-last_submit[h];last_submit[h]=now;
 /* One launch IRQ in addition to completion IRQ, inclusive handler budget. */
 joint_charge(SPI_IRQ,irq_cycles);return ESP_OK;
}
#include "joint_owner.inc"
static void task0(void){
 while(!outcome&&!runtime.stop&&capture.unit<limit){uint64_t begin=now;
  ++iterations[0];joint_charge(OWNER_SHELL,COST_OWNER_SHELL);
  if(!owner_iteration(&runtime))break;
  if(now-begin>max_owner_gap)max_owner_gap=now-begin;
 }
 stopped[0]=1;swapcontext(&contexts[0],&scheduler);abort();
}
static void task1(void){
 while(!outcome&&!runtime.stop&&!stopped[0]){++iterations[1];joint_charge(WORKER_SHELL,COST_WORKER_SHELL);
  if(!pack_slice(&runtime,1))break;feed(&runtime,1,false);
 }stopped[1]=1;swapcontext(&contexts[1],&scheduler);abort();
}
/* Called at real state-change sites in the generated C. */
void joint_accept(unsigned b){accepted[b]=now;
 uint64_t occupancy=pack.reserved-pack.retired*S3_PP_TX_BYTES;
 if(occupancy>peak_bytes)peak_bytes=occupancy;
}
void joint_publish(unsigned b){
 if(now-accepted[b]>max_publish_latency)max_publish_latency=now-accepted[b];
}
void joint_deadline(uint64_t d){if(d>now&&d-now<min_deadline)min_deadline=d-now;}
int main(int argc,char**argv){
 assert(argc==9);prepare_per_iteration=atoi(argv[7]);prepare_per_poll=atoi(argv[8]);assert(prepare_per_iteration>=prepare_per_poll&&prepare_per_poll==1024);unsigned rate=atoi(argv[1]);slice=atoi(argv[2]);limit=strtoull(argv[3],0,10);irq_cycles=atoi(argv[4]);stall_percent=atoi(argv[5]);
 assert((rate==16||rate==40)&&slice&&limit&&irq_cycles);cpp=240/rate;share=S3_PP_CORE0_SIXTEENTHS;
 uint8_t*buffers[4]={payload[0],payload[1],payload[2],payload[3]};assert(s3_pp_init(&pack,buffers)==S3_PP_OK);
 s3_native_io io={rd,wr,0,bank,0};
 assert(s3_pp_native_start_clocked(&capture,&pack,io,rate,joint_now,0,0));
 runtime.config.capture=&capture;runtime.config.pack=&pack;runtime.config.slice_pairs=slice;runtime.config.epoch=1;
 for(unsigned c=0;c<2;c++){runtime.config.ports[c]=&ports[c];runtime.config.transfers[c]=&tx[c];runtime.config.slice_bound[c]=strtoull(argv[6],0,10);runtime.next_feed[c]=600000000;}
 runtime.config.watchdog.timeout_ms=5000;
 for(unsigned c=0;c<2;c++){getcontext(&contexts[c]);contexts[c].uc_stack.ss_sp=stacks[c];contexts[c].uc_stack.ss_size=sizeof(stacks[c]);contexts[c].uc_link=&scheduler;makecontext(&contexts[c],c?task1:task0,0);}
 started=1;next_tick=2400000;irq_at[0]=irq_at[1]=UINT64_MAX;
 while(!stopped[0]&&!outcome){
  unsigned c=stopped[1]||ready[0]<=ready[1]?0:1;uint64_t t=ready[c];
  uint64_t event=next_tick;if(irq_at[0]<event)event=irq_at[0];if(irq_at[1]<event)event=irq_at[1];
  if(event<=t){advance(event);
   if(event==next_tick){for(unsigned k=0;k<2;k++){ready[k]+=2000;charged[k][TICK_IRQ]+=2000;counts[k][TICK_IRQ]++;interrupts[k]+=2000;}next_tick+=2400000;}
   for(unsigned h=0;h<2;h++)if(irq_at[h]==event){ready[0]+=irq_cycles;charged[0][SPI_IRQ]+=irq_cycles;counts[0][SPI_IRQ]++;interrupts[0]+=irq_cycles;irq_at[h]=UINT64_MAX;}
   continue;
  }
  advance(t);core=c;swapcontext(&scheduler,&contexts[c]);
  if(now>2400000000ULL){outcome=91;break;}
 }
 printf("{\"accept_reject_reason\":%u,\"attempted_arena_bytes\":%llu,",accept_reject_reason,(unsigned long long)attempted_arena_bytes);
 printf("\"prepare_per_iteration\":%u,\"prepare_per_poll\":%u,",prepare_per_iteration,prepare_per_poll);
 printf("\"slice_admission_bound\":%llu,\"failed_admission_remaining\":%llu,\"max_sampled_pack_cycles\":[%llu,%llu],",(unsigned long long)runtime.config.slice_bound[0],(unsigned long long)failed_admission_remaining,(unsigned long long)max_sampled_pack[0],(unsigned long long)max_sampled_pack[1]);
 printf("\"failure_written\":%u,\"failure_prepared\":%u,\"failure_prepare_done\":%u,\"completion_to_reap_cycles\":[%llu,%llu],\"accounted_until_cycles\":[%llu,%llu],",failure_written,failure_prepared,failure_prepare_done,(unsigned long long)max_wire_to_reap[0],(unsigned long long)max_wire_to_reap[1],(unsigned long long)ready[0],(unsigned long long)ready[1]);
 uint64_t demand[2]={0,0};for(unsigned c=0;c<2;c++)for(unsigned k=0;k<CATEGORIES;k++)demand[c]+=charged[c][k];
 printf("\"rate\":%u,\"share\":%u,\"slice_pairs\":%u,\"irq_cycles\":%u,\"stall_percent\":%u,\"cycles\":%llu,\"banks\":%u,\"native_fault\":%u,\"pack_fault\":%u,\"task_fault\":%u,\"outcome\":%u,\"iterations\":[%llu,%llu],\"polls\":%llu,\"peak_arena_bytes\":%llu,\"max_rf_poll_gap\":%llu,\"max_owner_iteration\":%llu,\"min_observed_job_deadline_margin\":%llu,\"max_publication_latency\":%llu,\"checked_bytes\":%llu,\"retired_bytes\":%llu,\"transfers_done\":[%llu,%llu],\"max_submit_gap\":[%llu,%llu],\"charged_cycles\":[%llu,%llu],\"stall_cycles\":[%llu,%llu],\"costs\":[",
 rate,share,slice,irq_cycles,stall_percent,(unsigned long long)now,capture.unit,capture.fault,atomic_load(&pack.fault),runtime.fault,outcome,
 (unsigned long long)iterations[0],(unsigned long long)iterations[1],(unsigned long long)polls,(unsigned long long)peak_bytes,(unsigned long long)max_poll_gap,(unsigned long long)max_owner_gap,(unsigned long long)min_deadline,(unsigned long long)max_publish_latency,(unsigned long long)checked_bytes,(unsigned long long)(pack.retired*S3_PP_TX_BYTES),(unsigned long long)transfers_done[0],(unsigned long long)transfers_done[1],(unsigned long long)max_submit_gap[0],(unsigned long long)max_submit_gap[1],(unsigned long long)demand[0],(unsigned long long)demand[1],(unsigned long long)stall[0],(unsigned long long)stall[1]);
 for(unsigned c=0;c<2;c++){printf("%s[",c?",":"");for(unsigned k=0;k<CATEGORIES;k++)printf("%s[%llu,%llu]",k?",":"",(unsigned long long)counts[c][k],(unsigned long long)charged[c][k]);printf("]");}puts("]}");
}

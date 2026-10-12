#include "s3_fft_exchange.h"
#include "s3_fft_tiles.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sched.h>
enum {FRAMES=12};
struct fake_device {spi_multi_transaction_t *batch;unsigned n;bool busy,complete;unsigned delay;};
static struct fake_device devices[2];
static _Alignas(16) int16_t input[FRAMES][16384],gold[FRAMES][16384],a[16384],b[16384];
static unsigned points,returned,read_pages;static bool ready_fault;static bool frozen;
extern const int16_t s3_fft_simd_table[8192];
extern int s3_pinned_fft_aes3(int16_t *,int,const int16_t *);
static bool service(void *ctx,unsigned core){(void)ctx;(void)core;return true;}
static int ready(void *ctx,unsigned epoch,uint32_t offset)
{(void)ctx;assert(epoch==17&&offset%4096==0);return ready_fault?-1:(!frozen&&offset<FRAMES*points*4);}
esp_err_t spi_bus_initialize(spi_host_device_t h,const spi_bus_config_t*c,int d){(void)h;(void)c;(void)d;return ESP_OK;}
esp_err_t spi_bus_free(spi_host_device_t h){(void)h;return ESP_OK;}
esp_err_t spi_bus_add_device(spi_host_device_t h,const spi_device_interface_config_t*c,spi_device_handle_t*p){(void)c;*p=&devices[h-2];return ESP_OK;}
esp_err_t spi_bus_remove_device(spi_device_handle_t d){(void)d;return ESP_OK;}
esp_err_t spi_bus_multi_trans_mode_enable(spi_device_handle_t d,bool b0){(void)d;(void)b0;return ESP_OK;}
esp_err_t spi_device_get_actual_freq(spi_device_handle_t d,int*f){(void)d;*f=80000;return ESP_OK;}
esp_err_t spi_device_queue_multi_trans(spi_device_handle_t d,spi_multi_transaction_t*s,unsigned n,int t)
{(void)t;assert(!d->busy);d->batch=s;d->n=n;d->busy=true;d->complete=false;d->delay=d==devices?35:3;return ESP_OK;}
esp_err_t spi_device_queue_trans(spi_device_handle_t d,spi_transaction_t*s,int t){return spi_device_queue_multi_trans(d,(spi_multi_transaction_t*)s,1,t);}
esp_err_t spi_device_get_multi_trans_result(spi_device_handle_t d,spi_multi_transaction_t**p,int t)
{(void)t;if(!d->complete)return ESP_ERR_TIMEOUT;*p=d->batch;d->busy=false;d->complete=false;return ESP_OK;}
esp_err_t spi_device_get_trans_result(spi_device_handle_t d,spi_transaction_t**p,int t)
{spi_multi_transaction_t*m=NULL;int rc=spi_device_get_multi_trans_result(d,&m,t);*p=m?&m->base:NULL;return rc;}
static void tick(void)
{
 for(unsigned p=0;p<2;++p) {
  struct fake_device*d=&devices[p];if(!d->busy||d->complete)continue;
  for(unsigned j=0;j<d->n;++j) {
   spi_transaction_t*s=&d->batch[j].base;
   unsigned off=(uint32_t)(s->addr>>16),frame=off/(4*points),page=off%(4*points);
   assert((s->addr>>48)==17&&(s->addr&65535)==4096&&frame<FRAMES&&page%4096==0);
   if(p==0) {assert(s->cmd==0xd712&&s->length==32768);assert(!memcmp(s->tx_buffer,(uint8_t*)gold[frame]+page,4096));}
   else {assert(s->cmd==0xd71b&&s->rxlength==32768);}
  }
  if(--d->delay==0) {
   for(unsigned j=0;j<d->n;++j) {
    spi_transaction_t*s=&d->batch[j].base;unsigned off=(uint32_t)(s->addr>>16),frame=off/(4*points),page=off%(4*points);
    if(p==1){memcpy(s->rx_buffer,(uint8_t*)input[frame]+page,4096);++read_pages;}
   }
   if(p==0){unsigned frame=(uint32_t)(d->batch[0].base.addr>>16)/(4*points);assert(frame==returned++);}
   d->complete=true;
  }
 }
}
int main(void)
{
 static _Alignas(16) StackType_t stack[2048/sizeof(StackType_t)];
 for(unsigned mode=0;mode<3;++mode) {
  points=(unsigned[]){2048,4096,8192}[mode];returned=read_pages=0;ready_fault=frozen=false;
  memset(devices,0,sizeof(devices));memset(a,0,sizeof(a));memset(b,0,sizeof(b));
  for(unsigned frame=0;frame<FRAMES;++frame) {
   for(unsigned i=0;i<2*points;++i)input[frame][i]=gold[frame][i]=(int16_t)((i*613+frame*7919)%16000-8000);
   assert(!s3_pinned_fft_aes3(gold[frame],points,s3_fft_simd_table));
   s3_fft_reverse_tile(gold[frame],points,0,points);
  }
  s3_fft_tasks tasks;s3_fft_exchange exchange;s3_spi_port ports[2];spi_multi_transaction_t octal[8],quad[1];spi_bus_config_t pins={0};
  assert(s3_fft_tasks_open(&tasks,stack,2048));
  assert(s3_spi_open(&ports[0],SPI2_HOST,&pins,10,8,true,octal,8)==ESP_OK);
  assert(s3_spi_open(&ports[1],SPI3_HOST,&pins,15,4,false,quad,1)==ESP_OK);
  assert(!s3_fft_exchange_open(&exchange,&ports[1],&ports[0],&tasks,a,a,s3_fft_simd_table,points,17,service,NULL,ready,NULL));
  assert(s3_fft_exchange_open(&exchange,&ports[1],&ports[0],&tasks,a,b,s3_fft_simd_table,points,17,service,NULL,ready,NULL));
  for(unsigned step=0;step<3000000&&exchange.completed<FRAMES;++step) {
   assert(s3_fft_exchange_step(&exchange));
   if(tasks.active)assert(s3_fft_tasks_owner_step(&tasks)!=S3_FFT_WORKER_ERROR);
   tick();if(step%100==0)sched_yield();
  }
  assert(exchange.completed==FRAMES&&returned==FRAMES&&read_pages==FRAMES*points/1024);
  assert(exchange.rx_slot==-1&&exchange.tx_slot==-1);
  assert(!s3_fft_exchange_drained(&exchange)); // peer still owns its static stack
  assert(s3_fft_exchange_open(&exchange,&ports[1],&ports[0],&tasks,a,b,s3_fft_simd_table,points,17,service,NULL,ready,NULL));
  assert(s3_fft_exchange_step(&exchange)&&exchange.rx_slot>=0);
  assert(s3_fft_tasks_stop(&tasks,2000));
  assert(!s3_fft_exchange_drained(&exchange)); // stop alone does not finish RX DMA
  for(unsigned i=0;i<3;++i)tick();
  assert(s3_fft_exchange_drained(&exchange)&&exchange.rx_slot==-1);
  assert(s3_fft_tasks_open(&tasks,stack,2048));
  assert(s3_fft_exchange_open(&exchange,&ports[1],&ports[0],&tasks,a,b,s3_fft_simd_table,points,17,service,NULL,ready,NULL));
  ready_fault=true;assert(!s3_fft_exchange_step(&exchange)&&exchange.fault);
  assert(!s3_fft_exchange_step(&exchange));assert(s3_fft_tasks_stop(&tasks,2000));
  assert(!s3_fft_exchange_drained(&exchange)); // status faults cannot silently adopt an epoch
  assert(s3_spi_close(&ports[0])==ESP_OK&&s3_spi_close(&ports[1])==ESP_OK);
 }
 puts("PASS actual SPI/task exchange: 36 full frames, all T modes, every bin, delayed DMA, two slot reuse, overlap reject, join/drain");
}

esp_err_t spi_device_acquire_bus(spi_device_handle_t d,unsigned t){(void)d;(void)t;return ESP_OK;}
void spi_device_release_bus(spi_device_handle_t d){(void)d;}
esp_err_t spi_device_polling_start(spi_device_handle_t d,spi_transaction_t *s,unsigned t){return spi_device_queue_trans(d,s,t);}
esp_err_t spi_device_polling_end(spi_device_handle_t d,unsigned t){spi_transaction_t *s=NULL;return spi_device_get_trans_result(d,&s,t);}
bool s3_test_spi_done(spi_host_device_t h){return devices[h-2].complete;}

#include "s3_rf_pump.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
enum {TOTAL=400};
struct fake_device {spi_multi_transaction_t *batch;unsigned n;bool busy,complete;int delay;};
static struct fake_device devices[2];
static bool visible[TOTAL];static uint8_t snapshots[TOTAL][4096];
static unsigned wire_pages,consumed,gray_reads,stops;
static bool unstable,spurious;static uint32_t rng=0xaacabc42;
static uint32_t random32(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static uint32_t sample(unsigned i){return (i*65537u+12345u)&0xfffff;}
static uint8_t expected(unsigned byte){unsigned pair=byte/5,shift=8*(byte%5);uint64_t v=sample(2*pair)|((uint64_t)sample(2*pair+1)<<20);return v>>shift;}
void s3_native_stop(s3_native_capture *s){s->running=false;++stops;}
static unsigned gpio(void *ctx){(void)ctx;++gray_reads;unsigned v=consumed&7;unsigned g=v^(v>>1);if(spurious)g=1;if(unstable&&(gray_reads&1))g^=1;return g;}
esp_err_t spi_bus_initialize(spi_host_device_t h,const spi_bus_config_t*c,int d){(void)h;(void)c;(void)d;return ESP_OK;}
esp_err_t spi_bus_free(spi_host_device_t h){(void)h;return ESP_OK;}
esp_err_t spi_bus_add_device(spi_host_device_t h,const spi_device_interface_config_t*c,spi_device_handle_t*p){(void)c;*p=&devices[h-2];return ESP_OK;}
esp_err_t spi_bus_remove_device(spi_device_handle_t d){(void)d;return ESP_OK;}
esp_err_t spi_bus_multi_trans_mode_enable(spi_device_handle_t d,bool b){(void)d;(void)b;return ESP_OK;}
esp_err_t spi_device_get_actual_freq(spi_device_handle_t d,int*f){(void)d;*f=80000;return ESP_OK;}
esp_err_t spi_device_queue_multi_trans(spi_device_handle_t d,spi_multi_transaction_t*b,unsigned n,int t)
{(void)t;assert(!d->busy);d->batch=b;d->n=n;d->busy=true;d->complete=false;d->delay=1+(random32()%6);return ESP_OK;}
esp_err_t spi_device_queue_trans(spi_device_handle_t d,spi_transaction_t*b,int t){return spi_device_queue_multi_trans(d,(spi_multi_transaction_t*)b,1,t);}
esp_err_t spi_device_get_multi_trans_result(spi_device_handle_t d,spi_multi_transaction_t**p,int t)
{(void)t;if(!d->complete)return ESP_ERR_TIMEOUT;*p=d->batch;d->busy=false;d->complete=false;return ESP_OK;}
esp_err_t spi_device_get_trans_result(spi_device_handle_t d,spi_transaction_t**p,int t)
{spi_multi_transaction_t*m=NULL;int rc=spi_device_get_multi_trans_result(d,&m,t);*p=m?&m->base:NULL;return rc;}
int main(void)
{
 static _Alignas(16) uint8_t payload[S3_RING_BYTES];
 s3_tx_ring ring;s3_iq10_packer packer;s3_rf_pump pump;s3_native_capture cap={0};
 s3_spi_port ports[2];spi_multi_transaction_t a[8],b[1];spi_bus_config_t pins={0};
 assert(s3_ring_init(&ring,payload,sizeof(payload),17)==S3_OK);s3_iq10_init(&packer,&ring);
 assert(s3_spi_open(&ports[0],SPI2_HOST,&pins,10,8,true,a,8)==ESP_OK);
 assert(s3_spi_open(&ports[1],SPI3_HOST,&pins,15,4,false,b,1)==ESP_OK);
 assert(s3_rf_pump_init(&pump,&ring,&cap,&ports[0],&ports[1],gpio,NULL));cap.running=true;
 unsigned input=0;unsigned total_samples=TOTAL*4096*2/5;
 // 400 pages is an exact 5-byte-pair boundary; sequence survives 50 Gray wraps.
 assert(TOTAL*4096%5==0);
 for(unsigned cycle=0;cycle<200000&&consumed<TOTAL;++cycle) {
  uint32_t source[127];unsigned n=total_samples-input;if(n>127)n=127;
  for(unsigned i=0;i<n;++i)source[i]=sample(input+i);
  size_t taken;int rc=s3_iq10_push(&packer,source,n,&taken);assert(rc==S3_OK||rc==S3_BUSY);input+=taken;
  assert(s3_rf_pump_step(&pump));assert(pump.submitted-pump.retired<=4);
  for(unsigned p=0;p<2;++p) {
   struct fake_device*d=&devices[p];if(!d->busy||d->complete)continue;
   // Actual leased data must remain immutable all the way to DMA completion.
   for(unsigned i=0;i<d->n;++i) {
    unsigned page=(uint32_t)(d->batch[i].base.addr>>16)/4096;
    const uint8_t *data=d->batch[i].base.tx_buffer;
    assert(page<TOTAL&&d->batch[i].base.length==32768&&d->batch[i].base.cmd==0xd711);
    for(unsigned k=0;k<4096;++k)assert(data[k]==expected(page*4096+k));
   }
   if(--d->delay==0) {
    for(unsigned i=0;i<d->n;++i) {
     unsigned page=(uint32_t)(d->batch[i].base.addr>>16)/4096;
     assert(!visible[page]);memcpy(snapshots[page],d->batch[i].base.tx_buffer,4096);visible[page]=true;++wire_pages;
    }
    d->complete=true;
   }
  }
  // FPGA consumes sorted committed pages independently of SDK reap order.
  if(visible[consumed]&&(random32()%7)!=0) {
   for(unsigned k=0;k<4096;++k)assert(snapshots[consumed][k]==expected(consumed*4096+k));
   ++consumed;
  }
 }
 assert(consumed==TOTAL&&wire_pages==TOTAL&&input==total_samples);
 for(unsigned i=0;i<5;++i)assert(s3_rf_pump_step(&pump));
 assert(ring.retire_sequence==TOTAL&&pump.retired==TOTAL&&pump.submitted==TOTAL);
 unsigned before=pump.retired;unstable=true;assert(s3_rf_pump_step(&pump));assert(before==pump.retired);unstable=false;
 spurious=true;assert(!s3_rf_pump_step(&pump));assert(pump.fault&&!cap.running&&stops);
 assert(!s3_rf_pump_step(&pump));
 puts("PASS 400 pages, native payload, DMA lease lifetime, Gray wraps, unstable sample, spurious-credit fail-stop");
}

esp_err_t spi_device_acquire_bus(spi_device_handle_t d,unsigned t){(void)d;(void)t;return ESP_OK;}
void spi_device_release_bus(spi_device_handle_t d){(void)d;}
esp_err_t spi_device_polling_start(spi_device_handle_t d,spi_transaction_t *s,unsigned t){return spi_device_queue_trans(d,s,t);}
esp_err_t spi_device_polling_end(spi_device_handle_t d,unsigned t){spi_transaction_t *s=NULL;return spi_device_get_trans_result(d,&s,t);}
bool s3_test_spi_done(spi_host_device_t h){return devices[h-2].complete;}

#include "s3_parallel_spi.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct fake_device {spi_multi_transaction_t *batch;unsigned n;bool busy,complete;int delay;};
static struct fake_device devices[2];
static bool queue_fail;
static unsigned random32(void){return 1;}
esp_err_t spi_bus_initialize(spi_host_device_t h,const spi_bus_config_t*c,int d){(void)h;(void)d;assert(c->max_transfer_sz==S3_PP_TX_BYTES);return ESP_OK;}
esp_err_t spi_bus_free(spi_host_device_t h){(void)h;return ESP_OK;}
esp_err_t spi_bus_add_device(spi_host_device_t h,const spi_device_interface_config_t*c,spi_device_handle_t*p){(void)c;*p=&devices[h-2];return ESP_OK;}
esp_err_t spi_bus_remove_device(spi_device_handle_t d){(void)d;return ESP_OK;}
esp_err_t spi_bus_multi_trans_mode_enable(spi_device_handle_t d,bool b){(void)d;(void)b;return ESP_OK;}
esp_err_t spi_device_get_actual_freq(spi_device_handle_t d,int*f){(void)d;*f=80000;return ESP_OK;}
esp_err_t spi_device_queue_multi_trans(spi_device_handle_t d,spi_multi_transaction_t*b,unsigned n,int t)
{(void)t;if(queue_fail)return ESP_ERR_INVALID_STATE;assert(!d->busy);d->batch=b;d->n=n;d->busy=true;d->complete=false;d->delay=1+(random32()%6);return ESP_OK;}
esp_err_t spi_device_queue_trans(spi_device_handle_t d,spi_transaction_t*b,int t){return spi_device_queue_multi_trans(d,(spi_multi_transaction_t*)b,1,t);}
esp_err_t spi_device_get_multi_trans_result(spi_device_handle_t d,spi_multi_transaction_t**p,int t)
{(void)t;if(!d->complete)return ESP_ERR_TIMEOUT;*p=d->batch;d->busy=false;d->complete=false;return ESP_OK;}
esp_err_t spi_device_get_trans_result(spi_device_handle_t d,spi_transaction_t**p,int t)
{spi_multi_transaction_t*m=NULL;int rc=spi_device_get_multi_trans_result(d,&m,t);*p=m?&m->base:NULL;return rc;}
esp_err_t spi_device_acquire_bus(spi_device_handle_t d,unsigned t){(void)d;(void)t;return ESP_OK;}
void spi_device_release_bus(spi_device_handle_t d){(void)d;}
esp_err_t spi_device_polling_start(spi_device_handle_t d,spi_transaction_t *s,unsigned t){return spi_device_queue_trans(d,s,t);}
esp_err_t spi_device_polling_end(spi_device_handle_t d,unsigned t){spi_transaction_t *s=NULL;return spi_device_get_trans_result(d,&s,t);}
bool s3_test_spi_done(spi_host_device_t h){return devices[h-2].complete;}

int main(void) {
 static _Alignas(16) uint8_t data[4][S3_PP_CHUNK];
 static uint32_t words[16384];
 s3_parallel_pack p;uint8_t*buffers[4]={data[0],data[1],data[2],data[3]};
 assert(s3_pp_init(&p,buffers)==S3_PP_OK);
 for(unsigned b=0;b<2;++b) {
  for(unsigned i=0;i<16384;++i)words[i]=i+b*16384;
  assert(s3_pp_accept(&p,b,words,0,16384,b*16384,0,100)==S3_PP_OK);
  unsigned n;
  for(unsigned w=0;w<2;++w)assert(s3_pp_step(&p,w,8192,0,1,&n)==S3_PP_OK);
  assert(s3_pp_collect(&p,0)==S3_PP_OK);
 }
 spi_bus_config_t pins={0};s3_spi_port ports[2];spi_multi_transaction_t descriptors[2];
 s3_pp_transfer x[2]={0};
 for(unsigned i=0;i<2;++i) {
  assert(s3_spi_open_bulk(&ports[i],i?SPI3_HOST:SPI2_HOST,&pins,10,i?4:8,&descriptors[i])==ESP_OK);
  assert(s3_pp_spi_submit(&x[i],&p,&ports[i],17)==ESP_OK);
  assert(x[i].active && descriptors[i].base.tx_buffer==data[(i*S3_PP_TX_BYTES)/S3_PP_CHUNK]+(i*S3_PP_TX_BYTES)%S3_PP_CHUNK);
  assert((uint32_t)(descriptors[i].base.addr>>16)==i*S3_PP_TX_BYTES);
  assert(descriptors[i].base.length==S3_PP_TX_BYTES*8);
  assert((descriptors[i].base.addr&65535)==S3_PP_TX_BYTES);
  assert(s3_pp_spi_reap(&x[i])==ESP_ERR_TIMEOUT);
 }
 assert(s3_pp_spi_submit(&x[0],&p,&ports[0],17)==ESP_ERR_INVALID_STATE);
 ports[1].device->complete=true;
 assert(s3_pp_spi_reap(&x[1])==ESP_OK && p.retired==0);
 ports[0].device->complete=true;
 assert(s3_pp_spi_reap(&x[0])==ESP_OK && p.retired==2);
 assert(s3_pp_spi_reap(&x[0])==ESP_ERR_INVALID_STATE);
 // Fill a third payload; failed queue must NOT retire/drop the taken buffer.
 assert(s3_pp_accept(&p,0,words,0,16384,32768,0,100)==S3_PP_OK);
 unsigned n;
 for(unsigned w=0;w<2;++w)assert(s3_pp_step(&p,w,8192,0,1,&n)==S3_PP_OK);
 assert(s3_pp_collect(&p,0)==S3_PP_OK);queue_fail=true;
 assert(s3_pp_spi_submit(&x[0],&p,&ports[0],17)==ESP_ERR_INVALID_STATE);
 assert(atomic_load(&p.fault) && x[0].active && ports[0].poisoned && p.retired==2);
 puts("PASS parallel-ring to bulk SPI leases, reverse completion, failed queue retains payload");
 return 0;
}

#include "s3_spi_transport.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct fake_device {spi_multi_transaction_t *batch;unsigned n;bool busy,complete;int delay;};
static struct fake_device devices[2];
static unsigned random32(void){return 1;}
esp_err_t spi_bus_initialize(spi_host_device_t h,const spi_bus_config_t*c,int d){(void)h;(void)d;assert(c->max_transfer_sz==32768);return ESP_OK;}
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
esp_err_t spi_device_acquire_bus(spi_device_handle_t d,unsigned t){(void)d;(void)t;return ESP_OK;}
void spi_device_release_bus(spi_device_handle_t d){(void)d;}
esp_err_t spi_device_polling_start(spi_device_handle_t d,spi_transaction_t *s,unsigned t){return spi_device_queue_trans(d,s,t);}
esp_err_t spi_device_polling_end(spi_device_handle_t d,unsigned t){spi_transaction_t *s=NULL;return spi_device_get_trans_result(d,&s,t);}
bool s3_test_spi_done(spi_host_device_t h){return devices[h-2].complete;}

int main(void) {
 static _Alignas(16) unsigned char data[S3_BULK_BYTES];
 spi_bus_config_t pins={0};
 for(unsigned lanes=4;lanes<=8;lanes+=4) {
  s3_spi_port p;spi_multi_transaction_t tx;
  int host=lanes==8 ? SPI2_HOST : SPI3_HOST;
  assert(s3_spi_open_bulk(&p,host,&pins,10,lanes,&tx)==ESP_OK);
  assert(s3_spi_use_polling(&p)==ESP_ERR_INVALID_STATE);
  assert(s3_spi_prepare_bulk(&p,0,0,data)==ESP_ERR_INVALID_ARG);
  assert(s3_spi_prepare_bulk(&p,1,1,data)==ESP_ERR_INVALID_ARG);
  assert(s3_spi_prepare_bulk(&p,1,0,data+1)==ESP_ERR_INVALID_ARG);
  assert(s3_spi_prepare(&p,S3_RF,1,0,data,1)==ESP_ERR_INVALID_ARG);
  assert(s3_spi_prepare_bulk(&p,17,0xfffff000u,data)==ESP_OK);
  assert(tx.base.cmd==0xd711 && tx.base.addr==0x0011fffff0008000ULL);
  assert(tx.base.length==32768*8 && tx.base.rxlength==0);
  assert(tx.base.tx_buffer==data && tx.base.rx_buffer==NULL);
  assert(s3_spi_queue(&p)==ESP_OK);
  assert(p.busy && p.device->n==1);
  assert(s3_spi_prepare_bulk(&p,17,0,data)==ESP_ERR_INVALID_STATE);
  assert(s3_spi_close(&p)==ESP_ERR_INVALID_STATE);
  assert(s3_spi_reap(&p)==ESP_ERR_TIMEOUT && p.busy);
  p.device->complete=true;
  assert(s3_spi_reap(&p)==ESP_OK && !p.busy);
  assert(s3_spi_prepare_bulk(&p,17,0,data)==ESP_OK);
  assert(s3_spi_prepare_bulk(&p,17,1,data)==ESP_ERR_INVALID_ARG);
  assert(s3_spi_queue(&p)==ESP_ERR_INVALID_STATE); // invalid prepare clears stale descriptor
  assert(s3_spi_close(&p)==ESP_OK);
 }
 puts("PASS bulk DMA descriptor and ownership on both hosts");
 return 0;
}

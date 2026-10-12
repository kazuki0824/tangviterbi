#include "s3_control.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct fake_device {spi_multi_transaction_t *batch;bool busy,complete;};
static struct fake_device device;static unsigned epoch,polling_ends;static bool cold;
static void put(uint8_t*p,uint32_t w){for(unsigned i=0;i<4;++i)p[i]=w>>(8*i);}
static void snapshot(uint8_t*p,uint32_t nonce,unsigned ep)
{uint32_t w[8]={0x31534353,0x01000000|ep,4096,5,nonce,0x1234abcd,0,0};for(unsigned i=0;i<6;++i)w[6]^=w[i];w[6]^=0x96c39a5f;for(unsigned i=0;i<8;++i)put(p+4*i,w[i]);}
esp_err_t spi_bus_initialize(spi_host_device_t h,const spi_bus_config_t*c,int d){(void)h;(void)c;(void)d;return ESP_OK;}
esp_err_t spi_bus_free(spi_host_device_t h){(void)h;return ESP_OK;}
esp_err_t spi_bus_add_device(spi_host_device_t h,const spi_device_interface_config_t*c,spi_device_handle_t*p){(void)h;(void)c;*p=&device;return ESP_OK;}
esp_err_t spi_bus_remove_device(spi_device_handle_t d){(void)d;return ESP_OK;}
esp_err_t spi_bus_multi_trans_mode_enable(spi_device_handle_t d,bool b){(void)d;(void)b;return ESP_OK;}
esp_err_t spi_device_get_actual_freq(spi_device_handle_t d,int*f){(void)d;*f=80000;return ESP_OK;}
esp_err_t spi_device_queue_multi_trans(spi_device_handle_t d,spi_multi_transaction_t*b,unsigned n,int t)
{(void)t;assert(n==1&&!d->busy);d->batch=b;d->busy=true;d->complete=false;return ESP_OK;}
esp_err_t spi_device_queue_trans(spi_device_handle_t d,spi_transaction_t*b,int t){return spi_device_queue_multi_trans(d,(spi_multi_transaction_t*)b,1,t);}
esp_err_t spi_device_get_multi_trans_result(spi_device_handle_t d,spi_multi_transaction_t**p,int t)
{(void)t;if(!d->complete)return ESP_ERR_TIMEOUT;*p=d->batch;d->busy=false;d->complete=false;return ESP_OK;}
esp_err_t spi_device_get_trans_result(spi_device_handle_t d,spi_transaction_t**p,int t)
{spi_multi_transaction_t*b=NULL;int rc=spi_device_get_multi_trans_result(d,&b,t);*p=b?&b->base:NULL;return rc;}
static void tick(void)
{assert(device.busy);spi_transaction_t*s=&device.batch->base;if(s->cmd==0xd71c){assert(!((s->addr>>48)&65535)&&(s->addr&65535)==32&&s->rxlength==256);if(!cold)snapshot(s->rx_buffer,(uint32_t)(s->addr>>16),epoch);}else{assert(s->cmd==0xd71d||s->cmd==0xd71e);assert((s->addr&65535)==0&&!s->length&&!s->rxlength);}device.complete=true;}
int main(void)
{
 uint8_t p[32],q[32];s3_control_status parsed;snapshot(p,123,17);
 assert(s3_control_decode(p,123,&parsed)&&parsed.image==0&&parsed.epoch==17&&parsed.IQ_offset==4096&&parsed.flags==5);
 assert(!s3_control_decode(p,124,&parsed));
 for(unsigned bit=0;bit<256;++bit){memcpy(q,p,32);q[bit/8]^=1u<<(bit%8);assert(!s3_control_decode(q,123,&parsed));}
 s3_spi_port port;spi_multi_transaction_t storage[1];spi_bus_config_t pins={0};s3_control ctl;
 assert(s3_spi_open(&port,SPI3_HOST,&pins,15,4,false,storage,1)==ESP_OK);assert(s3_spi_use_polling(&port)==ESP_OK);assert(s3_control_init(&ctl,&port));
 cold=true;assert(s3_control_query(&ctl)==ESP_OK);assert(!ctl.valid&&port.busy);assert(s3_control_poll(&ctl)==0&&polling_ends==0);
 assert(s3_control_query(&ctl)==ESP_ERR_INVALID_STATE);tick();assert(s3_control_poll(&ctl)==0&&!ctl.valid&&!port.busy);
 cold=false;assert(s3_control_query(&ctl)==ESP_OK);tick();assert(s3_control_poll(&ctl)==1&&ctl.valid&&ctl.status.epoch==0);
 assert(s3_control_epoch(&ctl,17)==ESP_OK);assert(!ctl.valid);tick();assert(s3_control_poll(&ctl)==1&&!ctl.valid);
 assert(s3_control_query(&ctl)==ESP_OK);tick();assert(s3_control_poll(&ctl)==1&&ctl.status.epoch==0);
 epoch=17;assert(s3_control_query(&ctl)==ESP_OK);tick();assert(s3_control_poll(&ctl)==1&&ctl.status.epoch==17);
 assert(s3_control_enable(&ctl,17,true)==ESP_OK);tick();assert(s3_control_poll(&ctl)==1);
 assert(s3_control_enable(&ctl,17,false)==ESP_OK);tick();assert(s3_control_poll(&ctl)==1);
 ctl.nonce=UINT32_MAX;assert(s3_control_query(&ctl)==ESP_ERR_INVALID_STATE&&ctl.fault);
 assert(s3_spi_close(&port)==ESP_OK);
 puts("PASS actual control adapter: 256 bit corruption checks, nonce, cold retry, request DMA vs actual epoch ACK, enable/disable, exhaustion");
}

esp_err_t spi_device_acquire_bus(spi_device_handle_t d,unsigned t){(void)d;(void)t;return ESP_OK;}
void spi_device_release_bus(spi_device_handle_t d){(void)d;}
esp_err_t spi_device_polling_start(spi_device_handle_t d,spi_transaction_t *s,unsigned t){return spi_device_queue_trans(d,s,t);}
esp_err_t spi_device_polling_end(spi_device_handle_t d,unsigned t){++polling_ends;assert(d->complete);spi_transaction_t *s=NULL;return spi_device_get_trans_result(d,&s,t);}
bool s3_test_spi_done(spi_host_device_t h){(void)h;return device.complete;}

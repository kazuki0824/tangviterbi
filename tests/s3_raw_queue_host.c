#include "s3_raw_queue.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct fake_device{spi_transaction_t*items[2];spi_transaction_t saved[2];unsigned head,count,done;};
static struct fake_device dev[2];static int failure;static bool mismatch;
esp_err_t spi_bus_initialize(spi_host_device_t h,const spi_bus_config_t*c,int d){(void)h;(void)d;assert(c->max_transfer_sz==S3_PP_TX_BYTES);return ESP_OK;}
esp_err_t spi_bus_free(spi_host_device_t h){(void)h;return ESP_OK;}
esp_err_t spi_bus_add_device(spi_host_device_t h,const spi_device_interface_config_t*c,spi_device_handle_t*d){assert(c->queue_size==2);*d=&dev[h-2];return ESP_OK;}
esp_err_t spi_bus_remove_device(spi_device_handle_t d){assert(!d->count);return ESP_OK;}
esp_err_t spi_device_get_actual_freq(spi_device_handle_t d,int*f){(void)d;*f=80000;return ESP_OK;}
esp_err_t spi_device_queue_trans(spi_device_handle_t d,spi_transaction_t*t,int wait){
 assert(wait==0);if(failure)return failure;assert(d->count<2);unsigned k=(d->head+d->count)%2;
 d->items[k]=t;d->saved[k]=*t;d->count++;return ESP_OK;
}
esp_err_t spi_device_get_trans_result(spi_device_handle_t d,spi_transaction_t**t,int wait){
 assert(wait==0);for(unsigned i=0;i<d->count;i++){unsigned k=(d->head+i)%2;assert(!memcmp(d->items[k],&d->saved[k],sizeof(**t)));}
 if(!d->done)return ESP_ERR_TIMEOUT;
 *t=mismatch?NULL:d->items[d->head];d->head^=1;d->count--;d->done--;return ESP_OK;
}
static _Alignas(16) uint8_t buffers[4][S3_PP_CHUNK];
static void setup(s3_parallel_pack*p,s3_raw_queue*q){
 memset(dev,0,sizeof(dev));memset(q,0,2*sizeof(*q));failure=0;mismatch=false;
 uint8_t*b[4]={buffers[0],buffers[1],buffers[2],buffers[3]};assert(s3_pp_init(p,b)==S3_PP_OK);
 p->published=4*S3_PP_CHUNK;spi_bus_config_t pins={0};
 for(unsigned h=0;h<2;h++)assert(s3_raw_queue_open(q+h,p,h+2,&pins,1,h?4:8,3)==ESP_OK);
}
int main(void){
 s3_parallel_pack p;s3_raw_queue q[2];setup(&p,q);
 for(unsigned h=0;h<2;h++)for(unsigned k=0;k<2;k++)assert(s3_raw_queue_submit(q+h)==ESP_OK);
 assert(p.submitted==4);assert(s3_raw_queue_submit(q)==ESP_ERR_NOT_FINISHED);assert(p.submitted==4);
 assert(s3_raw_queue_reap(q)==ESP_ERR_TIMEOUT);assert(s3_raw_queue_close(q)==ESP_ERR_INVALID_STATE);
 dev[1].done=2;assert(s3_raw_queue_reap(q+1)==ESP_OK);assert(s3_raw_queue_reap(q+1)==ESP_OK);assert(p.retired==0);
 dev[0].done=1;assert(s3_raw_queue_reap(q)==ESP_OK);assert(q[0].count==1&&dev[0].count==1);assert(p.retired==1);
 if(S3_PP_LEASES>4){assert(s3_raw_queue_submit(q)==ESP_OK);assert(q[0].count==2);dev[0].done=2;}else dev[0].done=1;
 while(q[0].count)assert(s3_raw_queue_reap(q)==ESP_OK);
 assert(p.retired==p.submitted);for(unsigned h=0;h<2;h++)assert(s3_raw_queue_close(q+h)==ESP_OK);
 setup(&p,q);assert(s3_raw_queue_submit(q)==ESP_OK);failure=ESP_ERR_TIMEOUT;
 assert(s3_raw_queue_submit(q)==ESP_ERR_TIMEOUT);assert(q[0].poisoned&&q[0].count==2&&p.submitted==2&&p.retired==0);assert(atomic_load(&p.fault));
 assert(s3_raw_queue_close(q)==ESP_ERR_INVALID_STATE);assert(s3_raw_queue_submit(q)==ESP_ERR_INVALID_STATE);
 setup(&p,q);assert(s3_raw_queue_submit(q)==ESP_OK);dev[0].done=1;mismatch=true;
 assert(s3_raw_queue_reap(q)==ESP_ERR_INVALID_STATE);assert(q[0].poisoned&&p.retired==0);
 puts("depth2, in-flight descriptor retention, reap while next active, cross-port prefix, queue failure and wrong completion checked");
}

#include "s3_raw_queue.h"
#include "esp_attr.h"
#include "esp_memory_utils.h"
#include <string.h>
static esp_err_t IRAM_ATTR poison(s3_raw_queue*q,esp_err_t error){
 q->poisoned=true;atomic_store_explicit(&q->pack->fault,S3_PP_FAULT,memory_order_relaxed);return error;
}
esp_err_t s3_raw_queue_open(s3_raw_queue*q,s3_parallel_pack*p,spi_host_device_t host,
 const spi_bus_config_t*pins,int cs,unsigned lanes,unsigned epoch){
 if(!q||!p||!pins||cs<0||!epoch||epoch>UINT16_MAX||(host!=SPI2_HOST&&host!=SPI3_HOST)||
    (lanes!=4&&lanes!=8)||(lanes==8&&host!=SPI2_HOST))return ESP_ERR_INVALID_ARG;
 /* Must be a fresh object. Never reopen an object that may own hardware. */
 if(q->device||q->count||q->poisoned)return ESP_ERR_INVALID_STATE;
 spi_bus_config_t bus=*pins;bus.max_transfer_sz=S3_PP_TX_BYTES;
 bus.flags=SPICOMMON_BUSFLAG_MASTER|(lanes==8?SPICOMMON_BUSFLAG_OCTAL:SPICOMMON_BUSFLAG_QUAD);
 esp_err_t rc=spi_bus_initialize(host,&bus,SPI_DMA_CH_AUTO);if(rc!=ESP_OK)return rc;
 spi_device_interface_config_t cfg={.command_bits=16,.address_bits=64,.mode=0,
  .clock_speed_hz=80000000,.spics_io_num=cs,.queue_size=2,.flags=SPI_DEVICE_HALFDUPLEX|SPI_DEVICE_NO_DUMMY};
 rc=spi_bus_add_device(host,&cfg,&q->device);
 if(rc!=ESP_OK){spi_bus_free(host);return rc;}
 int khz=0;rc=spi_device_get_actual_freq(q->device,&khz);
 if(rc!=ESP_OK||khz!=80000){spi_bus_remove_device(q->device);spi_bus_free(host);q->device=NULL;return rc!=ESP_OK?rc:ESP_ERR_NOT_SUPPORTED;}
 q->host=host;q->pack=p;q->head=0;q->count=0;
 memset(q->transactions,0,sizeof(q->transactions));
 for(unsigned i=0;i<2;i++){
  spi_transaction_t*t=&q->transactions[i];
  t->flags=(lanes==8?SPI_TRANS_MODE_OCT:SPI_TRANS_MODE_QIO)|SPI_TRANS_MULTILINE_CMD|SPI_TRANS_MULTILINE_ADDR|SPI_TRANS_DMA_BUFFER_ALIGN_MANUAL;
  t->cmd=0xd711;t->addr=((uint64_t)epoch<<48)|S3_PP_TX_BYTES;t->length=S3_PP_TX_BYTES*8;t->user=q;
 }
 return ESP_OK;
}
esp_err_t IRAM_ATTR s3_raw_queue_submit(s3_raw_queue*q){
 if(!q||!q->device||!q->pack||q->poisoned)return ESP_ERR_INVALID_STATE;
 if(q->count==2)return ESP_ERR_NOT_FINISHED;
 uint64_t seq;const uint8_t*data;int rc=s3_pp_take(q->pack,&seq,&data);
 if(rc==S3_PP_EMPTY)return ESP_ERR_NOT_FINISHED;
 if(rc!=S3_PP_OK)return ESP_ERR_INVALID_STATE;
 unsigned slot=(q->head+q->count)&1;q->sequences[slot]=seq;q->count++;
 if(((uintptr_t)data&3)||!esp_ptr_internal(data)||!esp_ptr_internal(data+S3_PP_TX_BYTES-1)||
    !esp_ptr_dma_capable(data)||!esp_ptr_dma_capable(data+S3_PP_TX_BYTES-1))return poison(q,ESP_ERR_INVALID_ARG);
 spi_transaction_t*t=&q->transactions[slot];
 t->addr=(t->addr&UINT64_C(0xffff00000000ffff))|((uint64_t)(uint32_t)(seq*S3_PP_TX_BYTES)<<16);
 t->tx_buffer=data;
 esp_err_t err=spi_device_queue_trans(q->device,t,0);
 return err==ESP_OK?ESP_OK:poison(q,err);
}
esp_err_t IRAM_ATTR s3_raw_queue_reap(s3_raw_queue*q){
 if(!q||!q->device||!q->pack||q->poisoned||!q->count)return ESP_ERR_INVALID_STATE;
 spi_transaction_t*done=NULL;esp_err_t err=spi_device_get_trans_result(q->device,&done,0);
 if(err==ESP_ERR_TIMEOUT)return err;
 if(err!=ESP_OK||done!=&q->transactions[q->head])return poison(q,err==ESP_OK?ESP_ERR_INVALID_STATE:err);
 if(s3_pp_complete(q->pack,q->sequences[q->head])!=S3_PP_OK)return poison(q,ESP_ERR_INVALID_STATE);
 q->head^=1;--q->count;return ESP_OK;
}
esp_err_t s3_raw_queue_close(s3_raw_queue*q){
 if(!q||!q->device||q->count||q->poisoned)return ESP_ERR_INVALID_STATE;
 esp_err_t rc=spi_bus_remove_device(q->device);if(rc!=ESP_OK)return rc;
 q->device=NULL;return spi_bus_free(q->host);
}

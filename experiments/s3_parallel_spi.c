#include "s3_parallel_spi.h"
#include "esp_attr.h"
esp_err_t IRAM_ATTR s3_pp_spi_submit(s3_pp_transfer*x,s3_parallel_pack*p,s3_spi_port*port,unsigned epoch) {
 if(!x || !p || !port || !epoch || epoch>UINT16_MAX)return ESP_ERR_INVALID_ARG;
 if(x->active || !port->bulk || port->busy || port->poisoned)return ESP_ERR_INVALID_STATE;
 const uint8_t*payload;uint64_t seq;
 int rc=s3_pp_take(p,&seq,&payload);
 if(rc==S3_PP_EMPTY)return ESP_ERR_NOT_FINISHED;
 if(rc!=S3_PP_OK)return ESP_ERR_INVALID_STATE;
 x->pack=p;x->port=port;x->sequence=seq;x->active=true;
 esp_err_t err=s3_spi_prepare_bulk(port,epoch,(uint32_t)(seq*S3_PP_CHUNK),(void*)payload);
 if(err==ESP_OK)err=s3_spi_queue(port);
 if(err!=ESP_OK)atomic_store_explicit(&p->fault,S3_PP_FAULT,memory_order_relaxed);
 return err;
}
esp_err_t IRAM_ATTR s3_pp_spi_reap(s3_pp_transfer*x) {
 if(!x || !x->active || !x->pack || !x->port)return ESP_ERR_INVALID_STATE;
 esp_err_t err=s3_spi_reap(x->port);
 if(err!=ESP_OK)return err;
 if(s3_pp_complete(x->pack,x->sequence)!=S3_PP_OK) {
  atomic_store_explicit(&x->pack->fault,S3_PP_FAULT,memory_order_relaxed);
  return ESP_ERR_INVALID_STATE;
 }
 x->active=false;return ESP_OK;
}

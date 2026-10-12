#include "s3_control.h"
#include "esp_memory_utils.h"
#include <string.h>
enum {QUERY=1,EPOCH=2,ENABLE=3};
static uint32_t word(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
bool s3_control_decode(const uint8_t*p,uint32_t nonce,s3_control_status*s)
{
 if(!p||!s)return false;
 uint32_t w[8];for(unsigned i=0;i<8;++i)w[i]=word(p+4*i);
 if(w[0]!=0x31534353||w[1]>>24!=1||((w[1]>>16)&255)>2||w[3]>31||w[4]!=nonce||w[7]||
  w[6]!=(w[0]^w[1]^w[2]^w[3]^w[4]^w[5]^0x96c39a5f))return false;
 *s=(s3_control_status){.image=(w[1]>>16)&255,.epoch=w[1]&65535,.IQ_offset=w[2],.flags=w[3],.build_tag=w[5],.nonce=w[4]};return true;
}
bool s3_control_init(s3_control*s,s3_spi_port*p)
{
 if(!s||!p||!p->device||p->busy||p->poisoned||p->sct||p->capacity!=1||p->lanes!=4||
  !esp_ptr_internal(s)||!esp_ptr_internal((uint8_t*)s+sizeof(*s)-1))return false;
 memset(s,0,sizeof(*s));s->port=p;return true;
}
static esp_err_t request(s3_control*s,unsigned kind,unsigned epoch,uint32_t arg)
{
 if(!s||s->fault||s->pending||!s->port||s->port->busy||s->port->poisoned)return ESP_ERR_INVALID_STATE;
 if(epoch>65535||(kind!=QUERY&&!epoch))return ESP_ERR_INVALID_ARG;
 s3_spi_port*p=s->port;spi_multi_transaction_t*d=p->segments;
 memset(d,0,sizeof(*d));d->base.flags=SPI_TRANS_MODE_QIO|SPI_TRANS_MULTILINE_CMD|SPI_TRANS_MULTILINE_ADDR|SPI_TRANS_DMA_BUFFER_ALIGN_MANUAL;
 d->base.cmd=kind==QUERY?0xd71c:kind==EPOCH?0xd71d:0xd71e;
 d->base.addr=((uint64_t)epoch<<48)|((uint64_t)arg<<16)|(kind==QUERY?S3_CONTROL_BYTES:0);
 if(kind==QUERY){memset(s->payload,0,sizeof(s->payload));d->base.rx_buffer=s->payload;d->base.rxlength=S3_CONTROL_BYTES*8;}
 d->base.user=s;p->count=1;s->pending=kind;s->valid=false;
 esp_err_t rc=s3_spi_queue(p);if(rc!=ESP_OK)s->fault=true;return rc;
}
esp_err_t s3_control_query(s3_control*s)
{
 if(!s||s->pending||!s->port||s->port->busy)return ESP_ERR_INVALID_STATE;
 // One outstanding query, zeroed RX buffer, and the RTL's fresh query/ACK
 // fence permit nonce wrap. A repeated 32-bit nonce is not an old core ACK.
 return request(s,QUERY,0,++s->nonce);
}
esp_err_t s3_control_epoch(s3_control*s,unsigned epoch){return request(s,EPOCH,epoch,0x45504f43);}
esp_err_t s3_control_enable(s3_control*s,unsigned epoch,bool enable){return request(s,ENABLE,epoch,enable);}
int s3_control_poll(s3_control*s)
{
 if(!s||s->fault||!s->pending)return -1;
 esp_err_t rc=s3_spi_reap(s->port);if(rc==ESP_ERR_TIMEOUT)return 0;
 if(rc!=ESP_OK){s->fault=true;return -1;}
 unsigned kind=s->pending;s->pending=0;
 if(kind!=QUERY)return 1;
 if(!s3_control_decode(s->payload,s->nonce,&s->status))return 0;
 s->valid=true;if(s->status.flags&10){s->fault=true;return -1;}return 1;
}
static int apply(s3_control*s,unsigned kind,unsigned epoch,bool enable)
{
 if(!s||s->fault||!s->port||!s->port->device||!epoch||epoch>65535)return -1;
 if(!s->apply_kind) {
  if(s->pending||s->port->busy)return 0;
  s->apply_kind=kind;s->apply_epoch=epoch;s->apply_enable=enable;s->apply_phase=0;
 }else if(s->apply_kind!=kind||s->apply_epoch!=epoch||s->apply_enable!=enable) {
  s->fault=true;return -1;
 }
 if(!s->apply_phase) {
  esp_err_t rc=kind==EPOCH?s3_control_epoch(s,epoch):s3_control_enable(s,epoch,enable);
  if(rc!=ESP_OK){s->fault=true;return -1;}
  s->apply_phase=1;return 0;
 }
 if(s->apply_phase==1||s->apply_phase==3) {
  int rc=s3_control_poll(s);if(rc<0)return -1;
  if(s->pending)return 0;
  if(s->apply_phase==3&&s->valid) {
   if(s->status.epoch>epoch){s->fault=true;return -1;}
   bool observed=s->status.epoch==epoch&&(kind==EPOCH?
    s->status.IQ_offset==0&&s->status.flags==4:
    ((s->status.flags&16)!=0)==enable);
   if(observed){s->apply_kind=0;s->apply_phase=0;return 1;}
  }
  s->apply_phase=2;
 }
 if(s->apply_phase==2) {
  if(s->port->busy)return 0;
  if(s3_control_query(s)!=ESP_OK){s->fault=true;return -1;}
  s->apply_phase=3;
 }
 return 0;
}
int s3_control_apply_epoch(s3_control*s,unsigned epoch){return apply(s,EPOCH,epoch,false);}
int s3_control_apply_enable(s3_control*s,unsigned epoch,bool enable){return apply(s,ENABLE,epoch,enable);}

#include "s3_fft_exchange.h"
#ifdef ESP_PLATFORM
#include "esp_memory_utils.h"
#include "esp_attr.h"
#include "s3_fft_tiles.h"
#include <string.h>
static bool fail(s3_fft_exchange *s){s->fault=true;return false;}
bool s3_fft_exchange_open(s3_fft_exchange *s,s3_spi_port *in,s3_spi_port *out,s3_fft_tasks *tasks,
 int16_t *a,int16_t *b,const int16_t *table,unsigned points,unsigned epoch,
 s3_fft_service_fn service,void *ctx,int (*ready)(void *,unsigned,uint32_t),void *ready_ctx)
{
 if(!s||!in||!out||in==out||!tasks||!tasks->peer||tasks->active||!a||!b||!table||!ready||!service||
    (points!=2048&&points!=4096&&points!=8192)||!epoch||epoch>65535||
    in->busy||out->busy||in->poisoned||out->poisoned||in->capacity!=1||out->capacity<points/1024||
    ((uintptr_t)a&15)||((uintptr_t)b&15)||((uintptr_t)table&15)||xPortGetCoreID()!=0)return false;
 size_t bytes=4*points;
 uintptr_t pa=(uintptr_t)a,pb=(uintptr_t)b,pt=(uintptr_t)table;
 if(pa>UINTPTR_MAX-bytes||pb>UINTPTR_MAX-bytes||pt>UINTPTR_MAX-8192*sizeof(int16_t)||
    (pa<pb+bytes&&pb<pa+bytes)||
    (pa<pt+8192*sizeof(int16_t)&&pt<pa+bytes)||
    (pb<pt+8192*sizeof(int16_t)&&pt<pb+bytes))return false;
 if(!esp_ptr_internal(a)||!esp_ptr_internal((uint8_t*)a+bytes-1)||!esp_ptr_dma_capable(a)||
    !esp_ptr_dma_capable((uint8_t*)a+bytes-1)||
    !esp_ptr_internal(b)||!esp_ptr_internal((uint8_t*)b+bytes-1)||!esp_ptr_dma_capable(b)||
    !esp_ptr_dma_capable((uint8_t*)b+bytes-1)||!esp_ptr_internal(table)||!esp_ptr_internal(table+8191))return false;
 memset(s,0,sizeof(*s));s->input=in;s->output=out;s->tasks=tasks;s->slots[0].data=a;s->slots[1].data=b;
 s->table=table;s->points=points;s->epoch=epoch;s->service=service;s->service_context=ctx;
 s->ready=ready;s->ready_context=ready_ctx;s->rx_slot=s->tx_slot=s->compute_slot=-1;return true;
}
static bool IRAM_ATTR reap(s3_fft_exchange *s)
{
 if(s->rx_slot>=0) {
  esp_err_t rc=s3_spi_reap(s->input);
  if(rc!=ESP_OK&&rc!=ESP_ERR_TIMEOUT)return fail(s);
  if(rc==ESP_OK) {
   s3_frame_slot *f=&s->slots[s->rx_slot];++f->pages_read;s->rx_slot=-1;
   if(f->pages_read==s->points/1024){f->state=S3_FRAME_READY;++s->next_read;}
  }
 }
 if(s->tx_slot>=0) {
  esp_err_t rc=s3_spi_reap(s->output);
  if(rc!=ESP_OK&&rc!=ESP_ERR_TIMEOUT)return fail(s);
  if(rc==ESP_OK){s->slots[s->tx_slot].state=S3_FRAME_FREE;s->tx_slot=-1;++s->next_write;++s->completed;}
 }
 return true;
}
bool IRAM_ATTR s3_fft_exchange_step(s3_fft_exchange *s)
{
 if(!s||s->fault||xPortGetCoreID()!=0)return false;
 if(!reap(s))return false;
 if(s->compute_slot>=0&&!s->tasks->active) {
  s->slots[s->compute_slot].state=S3_FRAME_REORDERING;s->slots[s->compute_slot].reordered=0;
  s->compute_slot=-1;++s->next_compute;
 }
 for(unsigned i=0;i<2;++i)if(s->slots[i].state==S3_FRAME_REORDERING) {
  s3_frame_slot *r=&s->slots[i];
  s3_fft_reverse_tile(r->data,s->points,r->reordered,r->reordered+64);
  r->reordered+=64;
  if(r->reordered==s->points)r->state=S3_FRAME_WRITING;
  break;
 }
 s3_frame_slot *f=&s->slots[s->next_write&1];
 if(s->tx_slot<0&&!s->output->busy&&f->state==S3_FRAME_WRITING&&f->sequence==s->next_write) {
  if(s3_spi_prepare(s->output,S3_FFT,s->epoch,f->offset,f->data,s->points/1024)!=ESP_OK)return fail(s);
  s->tx_slot=s->next_write&1;
  if(s3_spi_queue(s->output)!=ESP_OK)return fail(s);
 }
 f=&s->slots[s->next_compute&1];
 if(s->compute_slot<0&&!s->tasks->active&&f->state==S3_FRAME_READY&&f->sequence==s->next_compute) {
  if(!s3_fft_tasks_begin(s->tasks,f->data,s->table,s->points,s->service,s->service_context))return fail(s);
  f->state=S3_FRAME_COMPUTING;s->compute_slot=s->next_compute&1;
 }
 f=&s->slots[s->next_read&1];
 if(s->rx_slot<0&&!s->input->busy&&(f->state==S3_FRAME_FREE||
     (f->state==S3_FRAME_READING&&f->sequence==s->next_read))) {
  uint32_t offset=s->next_read*(uint32_t)(4*s->points);
  unsigned page=f->state==S3_FRAME_FREE?0:f->pages_read;
  int ready=s->ready(s->ready_context,s->epoch,offset+page*S3_PAGE_BYTES);
  if(ready<0||ready>1)return fail(s);
  if(ready) {
   if(f->state==S3_FRAME_FREE){f->state=S3_FRAME_READING;f->sequence=s->next_read;f->offset=offset;f->pages_read=0;}
   if(s3_spi_prepare(s->input,S3_IQ,s->epoch,offset+page*S3_PAGE_BYTES,
                     (uint8_t*)f->data+page*S3_PAGE_BYTES,1)!=ESP_OK)return fail(s);
   s->rx_slot=s->next_read&1;
   if(s3_spi_queue(s->input)!=ESP_OK)return fail(s);
  }
 }
 return true;
}
bool s3_fft_exchange_drained(s3_fft_exchange *s)
{
 if(!s||s->fault||s->tasks->peer||s->tasks->active)return false;
 if(!reap(s)||s->rx_slot>=0||s->tx_slot>=0)return false;
 return !s->input->busy&&!s->output->busy&&!s->input->poisoned&&!s->output->poisoned;
}
#endif

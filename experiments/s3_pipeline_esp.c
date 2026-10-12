#include "s3_pipeline_esp.h"
#ifdef ESP_PLATFORM
#include "driver/gpio.h"
#include "esp_attr.h"
#include "soc/soc.h"
#include "soc/gpio_reg.h"
#include <string.h>
static unsigned IRAM_ATTR gray(void *unused)
{(void)unused;return (REG_READ(GPIO_IN1_REG)>>6)&3;}
bool s3_pipeline_esp_open(s3_pipeline_esp *s,void *buffer,StackType_t *stack,
                          unsigned bytes,unsigned epoch,bool verified)
{
 if(!s||s->opened||!verified||xPortGetCoreID()!=0||!epoch||epoch>65535)return false;
 memset(s,0,sizeof(*s));
 if(s3_ring_init(&s->ring,buffer,S3_RING_BYTES,epoch)!=S3_OK)return false;
 s3_capture_init(&s->bridge,&s->ring);
 gpio_config_t control={.pin_bit_mask=(UINT64_C(1)<<38)|(UINT64_C(1)<<39),
  .mode=GPIO_MODE_INPUT,.pull_up_en=GPIO_PULLUP_DISABLE,.pull_down_en=GPIO_PULLDOWN_DISABLE,.intr_type=GPIO_INTR_DISABLE};
 if(gpio_config(&control)!=ESP_OK)return false;
 spi_bus_config_t a={.sclk_io_num=12,.mosi_io_num=11,.miso_io_num=13,
  .quadwp_io_num=14,.quadhd_io_num=9,.data4_io_num=4,.data5_io_num=5,.data6_io_num=6,.data7_io_num=7};
 spi_bus_config_t b={.sclk_io_num=16,.mosi_io_num=17,.miso_io_num=18,
  .quadwp_io_num=8,.quadhd_io_num=21,.data4_io_num=-1,.data5_io_num=-1,.data6_io_num=-1,.data7_io_num=-1};
 if(s3_spi_open(&s->ports[0],SPI2_HOST,&a,10,8,true,s->octal,8)!=ESP_OK)return false;
 if(s3_spi_open(&s->ports[1],SPI3_HOST,&b,15,4,false,s->quad,1)!=ESP_OK) {
  s3_spi_close(&s->ports[0]);return false;
 }
 if(!s3_rf_pump_init(&s->pump,&s->ring,&s->capture,&s->ports[0],&s->ports[1],gray,NULL)||
    !s3_fft_tasks_open(&s->tasks,stack,bytes)) {
  s3_spi_close(&s->ports[1]);s3_spi_close(&s->ports[0]);return false;
 }
 s->opened=true;return true;
}
bool s3_pipeline_esp_start_RF(s3_pipeline_esp *s,unsigned rate,unsigned words,uint32_t bound)
{
 if(!s||!s->opened||s->capture.running||!words||words>256||!bound||xPortGetCoreID()!=0)return false;
 s->pump.quad_RF_allowed=rate==40;
 s->service=(s3_fft_capture_service){.capture=&s->capture,.max_words=words,.slice_bound=bound,
  .pump=s3_rf_pump_step,.pump_context=&s->pump};
 return s3_native_start(&s->capture,&s->bridge,s3_native_mmio(),rate);
}
bool IRAM_ATTR s3_pipeline_esp_step(s3_pipeline_esp *s)
{
 if(!s||!s->opened||xPortGetCoreID()!=0)return false;
 if(s->FFT_enabled&&!s3_fft_exchange_step(&s->exchange)){s3_native_stop(&s->capture);return false;}
 if(s->tasks.active) {
  if(s3_fft_tasks_owner_step(&s->tasks)!=S3_FFT_WORKER_ERROR)return true;
  s3_native_stop(&s->capture);return false;
 }
 return s3_fft_service_capture(&s->service,0);
}
bool s3_pipeline_esp_begin_FFT(s3_pipeline_esp *s,int16_t *frame,const int16_t *table,unsigned points)
{
 if(!s||!s->opened||s->FFT_enabled||!s->capture.running)return false;
 // Called only after every inbound DMA page has completed. The caller
 // retains the full frame through this worker AND the return DMA.
 return s3_fft_tasks_begin(&s->tasks,frame,table,points,s3_fft_service_capture,&s->service);
}
bool s3_pipeline_esp_enable_FFT(s3_pipeline_esp *s,int16_t *a,int16_t *b,const int16_t *table,
 unsigned points,int (*ready)(void *,unsigned,uint32_t),void *ctx)
{
 if(!s||!s->opened||s->FFT_enabled||!s->capture.running||s->capture.cpp!=15)return false;
 if(!s3_fft_exchange_open(&s->exchange,&s->ports[1],&s->ports[0],&s->tasks,a,b,table,
    points,s->ring.epoch,s3_fft_service_capture,&s->service,ready,ctx))return false;
 s->FFT_enabled=true;return true;
}
bool s3_pipeline_esp_close(s3_pipeline_esp *s,TickType_t timeout)
{
 if(!s||!s->opened||xPortGetCoreID()!=0)return false;
 s3_native_stop(&s->capture);
 if(s->tasks.peer&&!s3_fft_tasks_stop(&s->tasks,timeout))return false;
 TickType_t begin=xTaskGetTickCount();
 while(s->pump.transfers[0].count||s->pump.transfers[1].count) {
  // Drain completed descriptors without submitting fresh RF.
  for(unsigned p=0;p<2;++p)if(s->pump.transfers[p].count) {
   esp_err_t rc=s3_rf_reap(&s->pump.transfers[p]);
   if(rc!=ESP_OK&&rc!=ESP_ERR_TIMEOUT)return false;
  }
  if((TickType_t)(xTaskGetTickCount()-begin)>=timeout)return false;
  vTaskDelay(1);
 }
 while(s->FFT_enabled&&!s3_fft_exchange_drained(&s->exchange)) {
  if(s->exchange.fault||(TickType_t)(xTaskGetTickCount()-begin)>=timeout)return false;
  vTaskDelay(1);
 }
 if(s->ports[0].busy||s->ports[1].busy)return false;
 if(s3_iq10_discard(&s->bridge.packer)!=S3_OK)return false;
 for(unsigned p=0;p<2;++p)if(s->ports[p].device&&s3_spi_close(&s->ports[p])!=ESP_OK)return false;
 s->opened=false;s->FFT_enabled=false;return true;
}
#endif

/* API/link probe only. No RF, SPI, task or 128-KiB receiver arena is started.
 * Do not interpret its free memory as a full receiver fit. */
#include "s3_raw_queue.h"
#include <stdio.h>
s3_raw_queue probe_queues[2];
s3_parallel_pack probe_pack;
esp_err_t (*volatile keep_open)(s3_raw_queue*,s3_parallel_pack*,spi_host_device_t,const spi_bus_config_t*,int,unsigned,unsigned)=s3_raw_queue_open;
esp_err_t (*volatile keep_submit)(s3_raw_queue*)=s3_raw_queue_submit;
esp_err_t (*volatile keep_reap)(s3_raw_queue*)=s3_raw_queue_reap;
esp_err_t (*volatile keep_close)(s3_raw_queue*)=s3_raw_queue_close;
int (*volatile keep_step)(s3_parallel_pack*,unsigned,unsigned,s3_pp_clock,void*,uint32_t,uint64_t,unsigned*)=s3_pp_step_clocked_quantized;
void app_main(void){
 printf("LINK ONLY queue=%u pack=%u anchors=%p %p %p %p %p storage=%p %p\n",
 (unsigned)sizeof(s3_raw_queue),(unsigned)sizeof(s3_parallel_pack),(void*)keep_open,(void*)keep_submit,
 (void*)keep_reap,(void*)keep_close,(void*)keep_step,(void*)probe_queues,(void*)&probe_pack);
}

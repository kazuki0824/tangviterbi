#include "s3_queue_receiver_open.h"
#include "esp_intr_alloc.h"
esp_err_t s3_queue_receiver_open(s3_raw_queue*q,s3_parallel_pack*p,
 spi_host_device_t host,const spi_bus_config_t*pins,int cs,unsigned lanes,unsigned epoch){
 if(!pins)return ESP_ERR_INVALID_ARG;
 spi_bus_config_t bus=*pins;
 bus.isr_cpu_id=ESP_INTR_CPU_AFFINITY_0;
 bus.intr_flags=ESP_INTR_FLAG_IRAM|ESP_INTR_FLAG_LEVEL1;
 return s3_raw_queue_open(q,p,host,&bus,cs,lanes,epoch);
}

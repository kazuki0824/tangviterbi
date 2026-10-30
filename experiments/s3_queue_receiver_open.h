#ifndef S3_QUEUE_RECEIVER_OPEN_H
#define S3_QUEUE_RECEIVER_OPEN_H
#include "s3_raw_queue.h"
/* RF-off setup for the costed receiver: both SPI IRQs on owner core 0,
 * non-shared level 1 and cache-safe. Pin routing is copied, not modified. */
esp_err_t s3_queue_receiver_open(s3_raw_queue*,s3_parallel_pack*,spi_host_device_t,
 const spi_bus_config_t*,int cs,unsigned lanes,unsigned epoch);
#endif

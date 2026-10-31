#ifndef S3_RAW_QUEUE_H
#define S3_RAW_QUEUE_H
#include "s3_parallel_pack.h"
#include "driver/spi_master.h"
/* Candidate raw-only queue. One coordinator owns both ports and pack leases.
 * queue_size=2, dedicated bus/device, IRQ core selected before open by caller.
 * No polling-running-command guard: a completed earlier transaction may be
 * available while the following transaction is still on the wire.
 * Failed submission poisons the queue and retains its lease. Recovery requires
 * stopping RF/workers and quiescing/removing DMA before reinitialization.
 */
typedef struct {
 spi_device_handle_t device;
 spi_host_device_t host;
 s3_parallel_pack *pack;
 spi_transaction_t transactions[2];
 uint64_t sequences[2];
 unsigned head,count;
 bool poisoned;
} s3_raw_queue;
esp_err_t s3_raw_queue_open(s3_raw_queue*,s3_parallel_pack*,spi_host_device_t,const spi_bus_config_t*,int cs,unsigned lanes,unsigned epoch);
esp_err_t s3_raw_queue_submit(s3_raw_queue*);
esp_err_t s3_raw_queue_reap(s3_raw_queue*);
esp_err_t s3_raw_queue_close(s3_raw_queue*);
#endif

#ifndef S3_RAW_TASKS_H
#define S3_RAW_TASKS_H
#include "s3_parallel_capture.h"
#include "s3_parallel_spi.h"
#include "s3_cycle_clock.h"
#ifdef ESP_PLATFORM
#include "esp_task_wdt.h"
/* Experimental task integration, not a measured schedule or board launcher.
 * Caller initializes PHY/SPI and fresh pack/storage before creating exactly
 * two pinned tasks above idle priority, one per entry argument. IRQ affinity is chosen at SPI init.
 * Caller exclusively owns TWDT configuration and supplies its ACTUAL current
 * configuration, not assumed defaults. No other code may reconfigure TWDT.
 * Keep config/state/stacks/ports alive until both tasks are deleted AND DMA is
 * reaped/reset. stopped[] means no more payload access, not task deletion or
 * DMA completion. Faults never cancel DMA or make a lease reusable.
 */
typedef struct {
 s3_parallel_pack *pack; s3_native_capture *capture;
 s3_spi_port *ports[2]; s3_pp_transfer *transfers[2];
 s3_native_io io;
 unsigned rate,epoch,slice_pairs;
 uint64_t slice_bound[2];
 esp_task_wdt_config_t watchdog;
} s3_raw_tasks_config;
typedef struct {
 s3_raw_tasks_config config;
 s3_cycle_clock_state clocks[2];
 atomic_uint ready[2],stopped[2],run,stop,fault;
 uint64_t next_feed[2];
} s3_raw_tasks;
typedef struct {s3_raw_tasks *runtime;unsigned core;} s3_raw_task_arg;
bool s3_raw_tasks_init(s3_raw_tasks*,const s3_raw_tasks_config*);
void s3_raw_tasks_request_stop(s3_raw_tasks*);
void s3_raw_task_entry(void*);
#endif
#endif

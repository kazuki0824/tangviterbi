/* Link-only memory probe, NOT a board-ready receiver. app_main never starts
 * RF, PHY, SPI or worker tasks. Kept entrypoints force real SDK linkage.
 * No pin map/tuner or measured scheduling bounds are supplied here.
 */
#include <stdint.h>
#include <stdio.h>
#include "esp_attr.h"
#include "esp_phy_init.h"
#include "esp_timer.h"
#include "heap_memory_layout.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "s3_parallel_capture.h"
#include "s3_timer_clock.h"
#include "s3_parallel_spi.h"
#include "hal/dma_types.h"

SOC_RESERVE_MEMORY_REGION(0x3fcb0000,0x3fce0000,s3_raw_RF_banks);
// Preserve the rev0 ROM tail [0x3fceee34,0x3fcf0000). Access upper arenas only
// after app_main, when startup stacks no longer occupy the recycled region.
SOC_RESERVE_MEMORY_REGION(0x3fce0000,0x3fce8000,s3_raw_bulk_upper0);
SOC_RESERVE_MEMORY_REGION(0x3fcf0000,0x3fcf8000,s3_raw_bulk_upper1);
DMA_ATTR uint8_t raw_lower_buffers[2][S3_PP_CHUNK];
s3_parallel_pack raw_pack;
s3_native_capture raw_capture;
s3_spi_port raw_ports[2];
spi_multi_transaction_t raw_descriptors[2];
s3_pp_transfer raw_transfers[2];
// Diagnostic reservation, not a measured stack high-water or safety margin.
// IDF's task creation interface uses bytes for stack depth.
enum { RAW_STACK_BYTES=4096 };
#if RAW_LATE_TASK_STACKS
// Entirely inside the app_main-recycled interval, below rev0 ROM data.
// The tasks are only created after app_main; no early heap may allocate here.
SOC_RESERVE_MEMORY_REGION(0x3fcea000,0x3fcec000,s3_raw_late_stacks);
StackType_t *const raw_task_stacks[2]={(StackType_t*)0x3fcea000,(StackType_t*)0x3fceb000};
#else
StackType_t raw_task_stacks[2][RAW_STACK_BYTES/sizeof(StackType_t)];
#endif
StaticTask_t raw_task_tcbs[2];
TaskHandle_t raw_task_handles[2];
const uint32_t raw_probe_sizes[]={sizeof(raw_pack),sizeof(raw_capture),sizeof(raw_ports),
 sizeof(raw_descriptors),sizeof(raw_transfers),2*RAW_STACK_BYTES,sizeof(raw_task_tcbs),
 sizeof(StaticTask_t),sizeof(dma_descriptor_align4_t),sizeof(StackType_t)};

// Dormant tasks reserve actual internal stacks/TCBs and retain task creation
// APIs. This is not a scheduler implementation or a slice-time assumption.
static void raw_worker_task(void *arg) {
 (void)arg;
 for(;;)ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
}
static void raw_create_tasks(void) {
 for(unsigned i=0;i<2;++i)
  raw_task_handles[i]=xTaskCreateStaticPinnedToCore(raw_worker_task,"raw-probe",
   RAW_STACK_BYTES,(void*)(uintptr_t)i,1,raw_task_stacks[i],&raw_task_tcbs[i],i);
}
static int raw_initialize_storage(void) {
 uint8_t *buffers[4]={raw_lower_buffers[0],raw_lower_buffers[1],
                     (uint8_t*)0x3fce0000,(uint8_t*)0x3fcf0000};
 return s3_pp_init(&raw_pack,buffers);
}
// Volatile function pointers preserve real SDK call graphs without executing
// undocumented RF register operations, guessed pins, or PHY initialization.
int (*volatile raw_keep_step)(s3_parallel_pack*,unsigned,unsigned,uint64_t,uint64_t,unsigned*)=s3_pp_step;
int (*volatile raw_keep_clocked_step)(s3_parallel_pack*,unsigned,unsigned,uint64_t,unsigned*)=s3_pp_step_timer;
uint64_t (*volatile raw_keep_clock)(void*)=s3_timer_clock;
void (*volatile raw_keep_tasks)(void)=raw_create_tasks;
int (*volatile raw_keep_storage)(void)=raw_initialize_storage;
void (*volatile raw_keep_phy)(esp_phy_modem_t)=esp_phy_enable;
bool (*volatile raw_keep_native)(s3_native_capture*,s3_parallel_pack*,s3_native_io,unsigned)=s3_pp_native_start_timer;
bool (*volatile raw_keep_poll)(s3_native_capture*)=s3_native_poll;
s3_native_io (*volatile raw_keep_mmio)(void)=s3_native_mmio;
int (*volatile raw_keep_collect)(s3_parallel_pack*,uint64_t)=s3_pp_collect;
esp_err_t (*volatile raw_keep_open)(s3_spi_port*,spi_host_device_t,const spi_bus_config_t*,int,unsigned,spi_multi_transaction_t*)=s3_spi_open_bulk;
esp_err_t (*volatile raw_keep_submit)(s3_pp_transfer*,s3_parallel_pack*,s3_spi_port*,unsigned)=s3_pp_spi_submit;
esp_err_t (*volatile raw_keep_reap)(s3_pp_transfer*)=s3_pp_spi_reap;

void app_main(void) {
 printf("RAW LINK PROBE ONLY: payload=%u task_storage=%u; no RF/SPI/tasks started\n",
        4*S3_PP_CHUNK,(unsigned)(2*RAW_STACK_BYTES+sizeof(raw_task_tcbs)));
 // Read volatile anchors to prevent linker GC. Never call them in app_main.
 printf("anchors=%p %p %p %p %p %p %p %p %p %p sizes=%p state=%p %p %p %p step=%p clock=%p stacks=%p clocked=%p\n",
  (void*)raw_keep_tasks,(void*)raw_keep_storage,(void*)raw_keep_phy,
  (void*)raw_keep_native,(void*)raw_keep_poll,(void*)raw_keep_mmio,
  (void*)raw_keep_collect,(void*)raw_keep_open,(void*)raw_keep_submit,(void*)raw_keep_reap,
  (void*)raw_probe_sizes,(void*)&raw_capture,(void*)raw_ports,(void*)raw_descriptors,(void*)raw_transfers,(void*)raw_keep_step,(void*)raw_keep_clock,(void*)raw_task_stacks,(void*)raw_keep_clocked_step);
}

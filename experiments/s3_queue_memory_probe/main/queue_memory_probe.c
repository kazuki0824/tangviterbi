/* Link-only combined storage diagnostic. No RF/SPI/task/PHY startup. */
#define app_main owner_link_probe_main
#include "../../s3_queue_owner_probe/main/queue_owner_probe.c"
#undef app_main
#include "esp_attr.h"
#include "esp_phy_init.h"
#include "heap_memory_layout.h"
SOC_RESERVE_MEMORY_REGION(0x3fcb0000,0x3fce0000,queue_RF_banks);
SOC_RESERVE_MEMORY_REGION(0x3fce0000,0x3fce8000,queue_payload_upper0);
SOC_RESERVE_MEMORY_REGION(0x3fcf0000,0x3fcf8000,queue_payload_upper1);
SOC_RESERVE_MEMORY_REGION(0x3fcea000,0x3fcec000,queue_late_stacks);
DMA_ATTR uint8_t queue_lower_payload[2][S3_PP_CHUNK];
StaticTask_t queue_task_tcbs[2];
s3_raw_launch queue_launch;
StackType_t *const queue_task_stacks[2]={(StackType_t*)0x3fcea000,(StackType_t*)0x3fceb000};
static int init_storage(void){
 uint8_t *buffers[4]={queue_lower_payload[0],queue_lower_payload[1],(uint8_t*)0x3fce0000,(uint8_t*)0x3fcf0000};
 return s3_pp_init(&owner_pack,buffers);
}
static bool create_tasks(const unsigned priorities[2]){
 StackType_t *stacks[2]={queue_task_stacks[0],queue_task_stacks[1]};
 StaticTask_t *tcbs[2]={&queue_task_tcbs[0],&queue_task_tcbs[1]};
 return s3_raw_tasks_launch(&owner_runtime,&queue_launch,stacks,tcbs,4096,priorities);
}
int (*volatile keep_storage)(void)=init_storage;
bool (*volatile keep_create)(const unsigned*)=create_tasks;
void (*volatile keep_phy)(esp_phy_modem_t)=esp_phy_enable;
s3_native_io (*volatile keep_mmio)(void)=s3_native_mmio;
esp_err_t (*volatile keep_open)(s3_raw_queue*,s3_parallel_pack*,spi_host_device_t,const spi_bus_config_t*,int,unsigned,unsigned)=s3_raw_queue_open;
void app_main(void){
 owner_link_probe_main();
 printf("MEMORY LINK ONLY: arena=%u stacks=8192 storage=%p create=%p phy=%p mmio=%p open=%p\n",4*S3_PP_CHUNK,(void*)keep_storage,(void*)keep_create,(void*)keep_phy,(void*)keep_mmio,(void*)keep_open);
}

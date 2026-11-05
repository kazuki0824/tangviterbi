/* Link-only memory/SDK probe. This program does not start RF, PHY, SPI or tasks. */
#include "tpre_sdk.h"
#include "esp_attr.h"
#include "esp_phy_init.h"
#include "heap_memory_layout.h"
#include <stddef.h>
#include <stdio.h>
#include <string.h>

SOC_RESERVE_MEMORY_REGION(0x3fcb0000,0x3fce8000,tpre_RF_and_upper_DMA0);
SOC_RESERVE_MEMORY_REGION(0x3fce9720,0x3fcee940,tpre_late_state_and_stacks);
SOC_RESERVE_MEMORY_REGION(0x3fcf0000,0x3fcf8000,tpre_upper_DMA1);
_Alignas(16) DMA_ATTR uint8_t tpre_lower_frames[4][TPRE_FRAME_BYTES];
tpre_sdk tpre_probe_sdk;
tpre_runtime tpre_probe_runtime;
s3_native_capture tpre_probe_capture;
StaticTask_t tpre_probe_tcbs[2];
enum { TPRE_PIPE_ADDRESS=0x3fce9720,TPRE_ADAPTER_ADDRESS=0x3fceb870,
       TPRE_STACK0_ADDRESS=0x3fcec940,TPRE_STACK1_ADDRESS=0x3fced940,TPRE_LATE_END=0x3fcee940 };
_Static_assert(sizeof(hbpipe)<=TPRE_ADAPTER_ADDRESS-TPRE_PIPE_ADDRESS,"pipeline reservation");
_Static_assert(sizeof(hbnative)<=TPRE_STACK0_ADDRESS-TPRE_ADAPTER_ADDRESS,"adapter reservation");
const uint32_t tpre_target_layout[]={2,sizeof(tpre_sdk),sizeof(tpre_runtime),sizeof(s3_native_capture),
 sizeof(hbpipe),sizeof(hbnative),sizeof(StaticTask_t),sizeof(spi_transaction_t),sizeof(s3_cycle_clock_state),
 offsetof(hbnative,banks),offsetof(hbnative,count),offsetof(hbnative,fill),offsetof(hbnative,last_time),
 offsetof(hbpipe,slots),sizeof(hbpipe_slot),offsetof(hbpipe_slot,status),offsetof(hbpipe_slot,output),
 TPRE_PIPE_ADDRESS,TPRE_ADAPTER_ADDRESS,TPRE_STACK0_ADDRESS,TPRE_STACK1_ADDRESS,TPRE_LATE_END};

/* The recycled SRAM is not C-zeroed. Repeating init while any task/DMA lease
 * survives would be unsafe; consume this attempt before touching the arena. */
static bool tpre_probe_storage_init(void) {
    static bool storage_attempted;
    if(storage_attempted)return false;
    storage_attempted=true;
    hbpipe *p=(hbpipe *)TPRE_PIPE_ADDRESS;hbnative *n=(hbnative *)TPRE_ADAPTER_ADDRESS;
    memset(n,0,sizeof(*n));
    if(hbpipe_init(p,10)!=HBPIPE_OK||hbnative_init(n,p,1)!=HBNATIVE_OK)return false;
    uint8_t *frames[TPRE_FRAMES]={tpre_lower_frames[0],tpre_lower_frames[1],tpre_lower_frames[2],tpre_lower_frames[3],
        (uint8_t *)0x3fce0000,(uint8_t *)0x3fce4000,(uint8_t *)0x3fcf0000,(uint8_t *)0x3fcf4000};
    if(!tpre_init(&tpre_probe_runtime,p,n,&tpre_probe_capture,frames,1,s3_cycle_clock_read,
        &tpre_probe_sdk.clocks[0],0,20000,tpre_sdk_io(&tpre_probe_sdk)))return false;
    esp_task_wdt_config_t watchdog={.timeout_ms=5000,.idle_core_mask=3,.trigger_panic=true};
    return tpre_sdk_init(&tpre_probe_sdk,&tpre_probe_runtime,&watchdog);
}
static bool tpre_probe_create(const unsigned priority[2]) {
    StackType_t *stacks[2]={(StackType_t *)TPRE_STACK0_ADDRESS,(StackType_t *)TPRE_STACK1_ADDRESS};
    StaticTask_t *tcbs[2]={&tpre_probe_tcbs[0],&tpre_probe_tcbs[1]};
    return tpre_sdk_launch(&tpre_probe_sdk,stacks,tcbs,4096,priority);
}
bool (*volatile tpre_keep_storage)(void)=tpre_probe_storage_init;
bool (*volatile tpre_keep_create)(const unsigned *)=tpre_probe_create;
bool (*volatile tpre_keep_open)(tpre_sdk *,const tpre_pins *)=tpre_sdk_open;
void (*volatile tpre_keep_phy)(esp_phy_modem_t)=esp_phy_enable;
void app_main(void) {
    printf("T SDK LINK ONLY: %p %p %p %p layout=%p; no RF/SPI/tasks started\n",
        (void *)tpre_keep_storage,(void *)tpre_keep_create,(void *)tpre_keep_open,(void *)tpre_keep_phy,
        (void *)tpre_target_layout);
}

#ifndef TPRE_SDK_H
#define TPRE_SDK_H
#include "tpre_runtime.h"
#include "s3_cycle_clock.h"
#include "driver/spi_master.h"
#include "esp_task_wdt.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

typedef struct tpre_sdk tpre_sdk;
typedef struct { tpre_sdk *sdk; unsigned core; } tpre_task_arg;
typedef struct { int clock, cs, data0, data1, data2, data3; } tpre_pins;
struct tpre_sdk {
    tpre_runtime *runtime;
    spi_device_handle_t device;
    spi_transaction_t transactions[TPRE_QUEUE_DEPTH];
    uint32_t sequence[TPRE_QUEUE_DEPTH];
    unsigned head, queued, epoch;
    bool initialized, open_attempted, poisoned, attempted;
    s3_cycle_clock_state clocks[2];
    uint64_t next_feed[2];
    esp_task_wdt_config_t watchdog;
    atomic_uint ready[2], stopped[2], run;
    tpre_task_arg args[2];
    TaskHandle_t handles[2];
};
/* Caller supplies the actual pre-receive TWDT configuration. RF must be off;
 * every object/frame must remain disjoint internal storage for the entire run.
 * Queue open and launch are one-shot. No restart/free API is provided.
 * stopped[] means payload quiescence, NOT task deletion, CP3 release, or DMA
 * completion. A poisoned queue retains every DMA lease until external reset.
 * Reception assumes flash cache enabled: linked SPI ISR helpers may be flash.
 */
bool tpre_sdk_init(tpre_sdk *,tpre_runtime *,const esp_task_wdt_config_t *);
bool tpre_sdk_open(tpre_sdk *,const tpre_pins *);
bool tpre_sdk_launch(tpre_sdk *,StackType_t *const[2],StaticTask_t *const[2],unsigned,const unsigned[2]);
tpre_io tpre_sdk_io(tpre_sdk *);
int tpre_sdk_submit(void *,unsigned,uint32_t,const void *,unsigned);
int tpre_sdk_reap(void *,uint32_t *);
bool tpre_sdk_feed(void *,unsigned);
void tpre_sdk_task(void *);
void tpre_pie_warmup(void);
#endif

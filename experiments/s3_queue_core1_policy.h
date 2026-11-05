#ifndef S3_QUEUE_CORE1_POLICY_H
#define S3_QUEUE_CORE1_POLICY_H
#include <stdbool.h>
#include "sdkconfig.h"
#include "esp_task.h"
#if CONFIG_ESP_TIMER_TASK_AFFINITY != 1 || !CONFIG_ESP_TIMER_ISR_AFFINITY_CPU1
#error "The core1 candidate requires both esp_timer task and interrupt on CPU1"
#endif
#if CONFIG_FREERTOS_UNICORE || CONFIG_ESP_PHY_DISABLE_PLL_TRACK
#error "The core1 candidate requires two cores and active PLL tracking"
#endif
/* A continuously runnable packing worker must not starve the PHY timer task.
 * This is a priority prerequisite, not a bound on IRQ/lock/hardware latency. */
static inline bool s3_queue_core1_priorities_valid(const unsigned priorities[2]) {
 return priorities && priorities[0] > 0 && priorities[1] > 0 &&
        priorities[0] < ESP_TASK_TIMER_PRIO && priorities[1] < ESP_TASK_TIMER_PRIO;
}
#endif

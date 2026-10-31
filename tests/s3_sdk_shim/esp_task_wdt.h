#ifndef TEST_ESP_TASK_WDT_H
#define TEST_ESP_TASK_WDT_H
#include "driver/spi_master.h"
#include "freertos/task.h"
enum {ESP_ERR_NOT_FOUND=6};
typedef struct {uint32_t timeout_ms,idle_core_mask;bool trigger_panic;} esp_task_wdt_config_t;
esp_err_t esp_task_wdt_add(TaskHandle_t);
esp_err_t esp_task_wdt_delete(TaskHandle_t);
esp_err_t esp_task_wdt_reset(void);
esp_err_t esp_task_wdt_status(TaskHandle_t);
esp_err_t esp_task_wdt_reconfigure(const esp_task_wdt_config_t*);
#endif

#ifndef TEST_TASK_H
#define TEST_TASK_H
#include "freertos/FreeRTOS.h"
#include <stdbool.h>
typedef struct host_task *TaskHandle_t;
typedef enum {eRunning,eReady,eBlocked,eSuspended,eDeleted} eTaskState;
TaskHandle_t xTaskCreateStaticPinnedToCore(void (*)(void*),const char*,unsigned,void*,unsigned,StackType_t*,StaticTask_t*,int);
unsigned ulTaskNotifyTake(int,TickType_t);
void xTaskNotifyGive(TaskHandle_t);
void vTaskSuspend(TaskHandle_t);
void vTaskDelete(TaskHandle_t);
void vTaskDelay(TickType_t);
TickType_t xTaskGetTickCount(void);
unsigned xPortGetCoreID(void);
unsigned uxTaskPriorityGet(TaskHandle_t);
eTaskState eTaskGetState(TaskHandle_t);
void taskYIELD(void);
#endif

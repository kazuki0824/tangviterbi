#ifndef S3_FFT_TASKS_H
#define S3_FFT_TASKS_H
#include "s3_fft_worker.h"
#ifdef ESP_PLATFORM
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
/* Main/core0 runs owner_step; one statically allocated core1 task executes
 * its tiles. Buffers remain exclusively owned until BOTH progress counters
 * finish. Stop joins core1 before reusing the state/stack/epoch. */
typedef struct {
 s3_fft_worker worker;
 StaticTask_t tcb;
 StackType_t *stack;
 unsigned stack_bytes;
 TaskHandle_t peer;
 atomic_uint command,ack;
 bool active;
} s3_fft_tasks;
bool s3_fft_tasks_open(s3_fft_tasks *,StackType_t *,unsigned stack_bytes);
bool s3_fft_tasks_begin(s3_fft_tasks *,int16_t *,const int16_t *,unsigned,
                       s3_fft_service_fn,void *);
int s3_fft_tasks_owner_step(s3_fft_tasks *);
bool s3_fft_tasks_stop(s3_fft_tasks *,TickType_t timeout);
#endif
#endif

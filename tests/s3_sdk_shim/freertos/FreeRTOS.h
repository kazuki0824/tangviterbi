#ifndef TEST_FREERTOS_H
#define TEST_FREERTOS_H
#include <stdint.h>
#include <pthread.h>
typedef uint32_t TickType_t;typedef uint32_t StackType_t;
typedef struct {unsigned placeholder;} StaticTask_t;
typedef pthread_mutex_t portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED PTHREAD_MUTEX_INITIALIZER
#define portENTER_CRITICAL(p) pthread_mutex_lock(p)
#define portEXIT_CRITICAL(p) pthread_mutex_unlock(p)
#define pdTRUE 1
#define configMAX_PRIORITIES 25
#define portMAX_DELAY UINT32_MAX
#endif

#define _POSIX_C_SOURCE 200809L
#include "s3_fft_tasks.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <sched.h>
struct host_task {pthread_t thread;pthread_mutex_t mutex;pthread_cond_t cv;unsigned notify;bool deleted;eTaskState state;void(*fn)(void*);void*arg;int core;};
static _Thread_local TaskHandle_t current;
unsigned xPortGetCoreID(void){return current?(unsigned)current->core:0;}
static void *run(void *p){current=p;current->fn(current->arg);return NULL;}
TaskHandle_t xTaskCreateStaticPinnedToCore(void(*fn)(void*),const char*n,unsigned bytes,void*arg,unsigned pri,StackType_t*stack,StaticTask_t*tcb,int core)
{(void)n;(void)pri;(void)tcb;assert(bytes==2048&&stack&&core==1);TaskHandle_t t=calloc(1,sizeof(*t));assert(t);t->fn=fn;t->arg=arg;t->core=core;t->state=eReady;pthread_mutex_init(&t->mutex,NULL);pthread_cond_init(&t->cv,NULL);assert(!pthread_create(&t->thread,NULL,run,t));return t;}
unsigned ulTaskNotifyTake(int clear,TickType_t wait)
{(void)clear;(void)wait;TaskHandle_t t=current;pthread_mutex_lock(&t->mutex);t->state=eBlocked;while(!t->notify&&!t->deleted)pthread_cond_wait(&t->cv,&t->mutex);unsigned n=t->notify;t->notify=0;t->state=eRunning;pthread_mutex_unlock(&t->mutex);return n;}
void xTaskNotifyGive(TaskHandle_t t){pthread_mutex_lock(&t->mutex);++t->notify;pthread_cond_signal(&t->cv);pthread_mutex_unlock(&t->mutex);}
void vTaskSuspend(TaskHandle_t unused)
{(void)unused;TaskHandle_t t=current;pthread_mutex_lock(&t->mutex);t->state=eSuspended;while(!t->deleted)pthread_cond_wait(&t->cv,&t->mutex);pthread_mutex_unlock(&t->mutex);pthread_exit(NULL);}
void vTaskDelete(TaskHandle_t t)
{pthread_mutex_lock(&t->mutex);assert(t->state==eSuspended);t->deleted=true;pthread_cond_signal(&t->cv);pthread_mutex_unlock(&t->mutex);pthread_join(t->thread,NULL);pthread_mutex_destroy(&t->mutex);pthread_cond_destroy(&t->cv);free(t);}
void vTaskDelay(TickType_t t){struct timespec delay={t/1000,(t%1000)*1000000};nanosleep(&delay,NULL);}
TickType_t xTaskGetTickCount(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
eTaskState eTaskGetState(TaskHandle_t t){pthread_mutex_lock(&t->mutex);eTaskState s=t->state;pthread_mutex_unlock(&t->mutex);return s;}
void taskYIELD(void){sched_yield();}

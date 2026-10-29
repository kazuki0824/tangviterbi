/* Link the actual queue-connected task lifecycle; do not start RF on a probe. */
#include "s3_queue_tasks.h"
#include <stdio.h>
s3_raw_tasks owner_runtime;
s3_raw_queue owner_queues[2];
s3_parallel_pack owner_pack;
s3_native_capture owner_capture;
void (*volatile keep_entry)(void*)=s3_raw_task_entry;
bool (*volatile keep_init)(s3_raw_tasks*,const s3_raw_tasks_config*)=s3_raw_tasks_init;
bool (*volatile keep_launch)(s3_raw_tasks*,s3_raw_launch*,StackType_t*const[2],StaticTask_t*const[2],unsigned,const unsigned[2])=s3_raw_tasks_launch;
void app_main(void){printf("OWNER LINK ONLY %p %p %p %p %p %p %p\n",(void*)keep_entry,(void*)keep_init,(void*)keep_launch,(void*)&owner_runtime,(void*)owner_queues,(void*)&owner_pack,(void*)&owner_capture);}

"""Run pinned queue.c bodies with host shims; no spinlock/time emulation."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_s3_spi_lock_primitives import function

ROOT = Path(__file__).resolve().parents[1]

SHIM = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#define configUSE_QUEUE_SETS 1
#define configUSE_MUTEXES 1
#define queueUSE_LOCKS 0
#define queueUNLOCKED 0
#define pdFALSE 0
#define pdTRUE 1
#define pdPASS 1
#define pdFAIL 0
#define errQUEUE_FULL 0
#define errQUEUE_EMPTY 0
#define queueSEND_TO_BACK 0
#define queueOVERWRITE 2
#define queueQUEUE_IS_MUTEX NULL
#define uxQueueType pcHead
typedef int BaseType_t;
typedef unsigned UBaseType_t;
typedef unsigned TickType_t;
typedef int TimeOut_t;
typedef struct Queue {
 int8_t *pcHead, *pcWriteTo;
 union {struct {int8_t *pcTail,*pcReadFrom;} xQueue;
        struct {void *xMutexHolder;} xSemaphore;} u;
 unsigned uxMessagesWaiting,uxLength,uxItemSize;
 int xQueueLock,xTasksWaitingToSend,xTasksWaitingToReceive;
 void *pxQueueSetContainer;
} Queue_t;
typedef Queue_t *QueueHandle_t;
static unsigned entries,exits,depth,copies,bytes;
static int forbidden(void){abort();return 0;}
static void enter(void){assert(depth==0);++depth;++entries;}
static void leave(void){assert(depth==1);--depth;++exits;}
static void *copy(void *dst,const void *src,size_t n){assert(depth==1);++copies;bytes+=n;return memcpy(dst,src,n);}
#define memcpy copy
#define configASSERT assert
#define taskENTER_CRITICAL(x) ((void)(x),enter())
#define taskEXIT_CRITICAL(x) ((void)(x),leave())
#define prvENTER_CRITICAL_OR_MASK_ISR(x,s) ((s)=0,taskENTER_CRITICAL(x))
#define prvEXIT_CRITICAL_OR_UNMASK_ISR(x,s) ((void)(s),taskEXIT_CRITICAL(x))
#define listLIST_IS_EMPTY(x) (*(x)==0)
#define mtCOVERAGE_TEST_MARKER() ((void)0)
#define portASSERT_IF_INTERRUPT_PRIORITY_INVALID() ((void)0)
#define xTaskRemoveFromEventList(...) forbidden()
#define prvNotifyQueueSetContainer(...) forbidden()
#define xTaskPriorityDisinherit(...) forbidden()
#define vTaskInternalSetTimeOutState(...) ((void)(&xTimeOut),forbidden())
#define xTaskCheckForTimeOut(...) forbidden()
#define vTaskPlaceOnEventList(...) forbidden()
#define queueYIELD_IF_USING_PREEMPTION() forbidden()
#define portYIELD_WITHIN_API() forbidden()
#define traceQUEUE_SEND(...) ((void)0)
#define traceQUEUE_SEND_FAILED(...) ((void)0)
#define traceQUEUE_RECEIVE(...) ((void)0)
#define traceQUEUE_RECEIVE_FAILED(...) ((void)0)
#define traceQUEUE_SEND_FROM_ISR(...) ((void)0)
#define traceQUEUE_SEND_FROM_ISR_FAILED(...) ((void)0)
#define traceQUEUE_RECEIVE_FROM_ISR(...) ((void)0)
#define traceQUEUE_RECEIVE_FROM_ISR_FAILED(...) ((void)0)
#define traceBLOCKING_ON_QUEUE_SEND(...) forbidden()
#define traceBLOCKING_ON_QUEUE_RECEIVE(...) forbidden()
'''

MAIN = r'''
int main(void){
 /* Four entry points, empty/full, one-slot ring wrap. Item is the saved
    ESP32-S3 ELF's 20-byte spi_trans_priv_t, not a 32-KiB payload. */
 for(unsigned api=0;api<4;++api)for(unsigned full=0;full<2;++full){
  uint8_t storage[20],input[20],output[20];
  for(unsigned i=0;i<20;++i)storage[i]=input[i]=(uint8_t)(i+17);
  memset(output,0,sizeof output);
  Queue_t q={.pcHead=(int8_t*)storage,.pcWriteTo=(int8_t*)storage,
   .u.xQueue={(int8_t*)storage+20,(int8_t*)storage},
   .uxMessagesWaiting=full,.uxLength=1,.uxItemSize=20};
  unsigned send=api<2;int woken=0,result;
  entries=exits=depth=copies=bytes=0;
  if(api==0)result=xQueueGenericSend(&q,input,0,queueSEND_TO_BACK);
  else if(api==1)result=xQueueGenericSendFromISR(&q,input,&woken,queueSEND_TO_BACK);
  else if(api==2)result=xQueueReceive(&q,output,0);
  else result=xQueueReceiveFromISR(&q,output,&woken);
  unsigned success=send?!full:full;
  assert(result==(int)success);assert(entries==1&&exits==1&&depth==0);
  assert(copies==success&&bytes==20*success);assert(woken==0);
  assert(q.uxMessagesWaiting==(success?(send?1:0):full));
  assert(q.xTasksWaitingToSend==0&&q.xTasksWaitingToReceive==0);
  if(success)assert(memcmp(send?storage:output,input,20)==0);
 }
 return 0;
}
'''


class QueuePathsTest(unittest.TestCase):
    def test_actual_four_queue_bodies_with_empty_wait_lists(self):
        source = (ROOT/'reports/s3-spi-wait-audit/sources/queue.c').read_text()
        names = ('prvCopyDataToQueue','prvCopyDataFromQueue','xQueueGenericSend',
                 'xQueueGenericSendFromISR','xQueueReceive','xQueueReceiveFromISR')
        code = SHIM + '\n'.join(function(source,name) for name in names) + MAIN
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'queue.c').write_text(code)
            result = subprocess.run(['cc','-std=c11','-Wall','-Werror',
                '-fsanitize=undefined',str(root/'queue.c'),'-o',str(root/'queue')],
                capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(root/'queue')],check=True)


if __name__ == '__main__':
    unittest.main()

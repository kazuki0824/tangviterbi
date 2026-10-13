#define _POSIX_C_SOURCE 200809L
#include "s3_fft_tasks.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <sched.h>
extern const int16_t s3_fft_simd_table[8192];
extern int s3_pinned_fft_aes3(int16_t *,int,const int16_t *);
static atomic_uint polls[2];static bool failure;
static bool service(void *ctx,unsigned core){(void)ctx;atomic_fetch_add(&polls[core],1);return !(failure&&core==0);}
int main(void)
{
 static _Alignas(16) StackType_t stack[2048/sizeof(StackType_t)];
 static _Alignas(16) int16_t data[16384],gold[16384];s3_fft_tasks tasks;
 assert(s3_fft_tasks_open(&tasks,stack,2048));
 for(unsigned pass=0;pass<6;++pass) {
  unsigned points=(unsigned[]){2048,4096,8192}[pass%3];
  for(unsigned i=0;i<points*2;++i)data[i]=gold[i]=(int16_t)((i*631+pass*7919)%16000-8000);
  assert(s3_pinned_fft_aes3(gold,points,s3_fft_simd_table)==0);
  assert(s3_fft_tasks_begin(&tasks,data,s3_fft_simd_table,points,service,NULL));
  assert(!s3_fft_tasks_begin(&tasks,data,s3_fft_simd_table,points,service,NULL));
  int result=0;
  for(unsigned i=0;i<1000000;++i){result=s3_fft_tasks_owner_step(&tasks);assert(result!=-1);if(result==2)break;if(i%1000==0)taskYIELD();}
  assert(result==2&&!tasks.active);assert(!memcmp(data,gold,points*4));
 }
 failure=true;assert(s3_fft_tasks_begin(&tasks,data,s3_fft_simd_table,8192,service,NULL));
 assert(s3_fft_tasks_owner_step(&tasks)==-1);
 assert(s3_fft_tasks_stop(&tasks,2000)&&!tasks.peer);
 // Reusing this static TCB/state/stack occurs only after a suspended peer joins.
 failure=false;assert(s3_fft_tasks_open(&tasks,stack,2048));assert(s3_fft_tasks_stop(&tasks,2000));
 printf("PASS actual task adapter, six complete frames, all T modes, pinned owners, failed frame join, safe reopen; polls=%u/%u\n",atomic_load(&polls[0]),atomic_load(&polls[1]));
}

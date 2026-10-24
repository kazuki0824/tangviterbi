/* Executes pinned, unmodified Espressif TLSF with a 32-bit host ABI.
 * This is a projected allocation trace, not ESP-IDF boot emulation.
 * Linux syscalls replace libc solely for reporting; allocator is unchanged.
 */
#include <stddef.h>
#include <stdint.h>
#include "tlsf.h"
_Static_assert(sizeof(void*)==4 && sizeof(size_t)==4,"32-bit ABI required");
static void emit(const char *s) {
 unsigned n=0;while(s[n])++n;
 unsigned syscall=4;
 __asm__ volatile("int $0x80":"+a"(syscall):"b"(1),"c"(s),"d"(n):"memory");
}
static void number(unsigned v) {
 char b[16];unsigned i=15;b[i]=0;do {b[--i]='0'+v%10;v/=10;}while(v);emit(b+i);
}
void replay_abort(void) {
 emit("ALLOCATOR_ASSERTION\n");
 __asm__ volatile("int $0x80"::"a"(1),"b"(90):"memory");
 __builtin_unreachable();
}
int printf(const char *fmt,...) { (void)fmt;replay_abort();return 0; }
void *memset(void *p,int c,size_t n) { unsigned char *d=p;for(size_t i=0;i<n;++i)d[i]=c;return p; }
void *memcpy(void *p,const void *q,size_t n) { unsigned char *d=p;const unsigned char *s=q;for(size_t i=0;i<n;++i)d[i]=s[i];return p; }
struct scenario { const char *name;unsigned lower,upper,rtc,main_stack,heap_records; };
#include "scenarios.h"
static unsigned char arenas[3][32768] __attribute__((aligned(16)));
static tlsf_t heaps[3];
static unsigned lengths[3],largest[3];
static bool measure(void *ptr,size_t size,int used,void *ctx) {
 (void)ptr;unsigned *m=ctx;if(!used && size>*m)*m=size;return true;
}
static void snapshot(void) {
 emit("[");
 for(unsigned h=0;h<3;++h) {
  largest[h]=0;tlsf_walk_pool(tlsf_get_pool(heaps[h]),measure,&largest[h]);
  if(tlsf_check(heaps[h])||tlsf_check_pool(tlsf_get_pool(heaps[h])))replay_abort();
  if(h)emit(",");number(largest[h]);
 }
 emit("]");
}
static int alloc(unsigned n,int forced) {
 // SDK capability priority: both DIRAM heaps before RTC; within DIRAM,
 // original heap size ascending, not current free bytes ascending.
 unsigned order[3]={lengths[0]<lengths[1]?0:1,lengths[0]<lengths[1]?1:0,2};
 for(unsigned i=0;i<3;++i) {
  unsigned h=order[i];if(forced>=0 && h!=(unsigned)forced)continue;
  if(tlsf_malloc(heaps[h],n))return h;
 }
 return -1;
}
static int event(const char *name,unsigned bytes,int forced,int comma) {
 if(comma)emit(",");emit("{\"name\":\"");emit(name);emit("\",\"bytes\":");number(bytes);
 int h=alloc(bytes,forced);emit(",\"heap\":");if(h<0)emit("null");else number(h);
 emit(",\"largest_free_blocks\":");snapshot();emit("}");return h>=0;
}
void _start(void) {
 emit("[");
 for(unsigned s=0;s<sizeof(scenarios)/sizeof(scenarios[0]);++s) {
  struct scenario c=scenarios[s];lengths[0]=c.lower;lengths[1]=c.upper;lengths[2]=c.rtc;
  for(unsigned h=0;h<3;++h) {
   // Target DWARF: multi_heap_info=20. Same wrapper offset as IDF.
   memset(arenas[h],0,sizeof(arenas[h]));heaps[h]=tlsf_create_with_pool(arenas[h]+20,lengths[h]-20,0);
   if(!heaps[h])replay_abort();
  }
  if(s)emit(",");emit("{\"name\":\"");emit(c.name);emit("\",\"initial_largest\":");snapshot();
  emit(",\"events\":[");unsigned comma=0;int ok=1;
  if(c.heap_records) {ok=event("heap_records",c.heap_records,0,comma++);}
  const char *names[]={"ipc0_stack","ipc0_TCB","ipc1_stack","ipc1_TCB","timer_stack","timer_TCB","main_stack","main_TCB","idle0_stack","idle0_TCB","idle1_stack","idle1_TCB"};
  unsigned sizes[]={1280,340,1280,340,4096,340,c.main_stack,340,1536,340,1536,340};
  // An actual SDK assert halts startup on a failed allocation. Preserve that
  // first failure, but continue all independent scenarios.
  for(unsigned e=0;e<12 && ok;++e)ok=event(names[e],sizes[e],-1,comma++);
  emit("],\"projected_trace_pass\":");emit(ok?"true":"false");emit("}");
 }
 emit("]\n");__asm__ volatile("int $0x80"::"a"(1),"b"(0):"memory");__builtin_unreachable();
}

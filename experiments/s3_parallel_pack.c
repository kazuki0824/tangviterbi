#include "s3_parallel_pack.h"
#include <stddef.h>
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#define HOT IRAM_ATTR
#else
#define HOT
#endif
#define S3_HOT HOT
#include "s3_iq10_block.h"
_Static_assert(sizeof(atomic_uint)==4,"32-bit publication state required");
enum { IDLE, READY, DONE };
enum { DMA_FREE, DMA_ACTIVE, DMA_DONE };
static int HOT fail(s3_parallel_pack *p, unsigned code) {
 // All concurrent writers publish a nonzero fault; exact first cause is not
 // ordered. No read-modify-write atomic or spinlock on the RF/worker path.
 atomic_store_explicit(&p->fault,code,memory_order_relaxed);
 return (int)code;
}
int s3_pp_init(s3_parallel_pack *p, uint8_t *const buffers[4]) {
 if(!p || !buffers) return S3_PP_INVALID;
 for(unsigned i=0;i<4;++i) {
  uintptr_t a=(uintptr_t)buffers[i];
  if(!a || (a&3) || a>UINTPTR_MAX-S3_PP_CHUNK) return S3_PP_INVALID;
  for(unsigned j=0;j<i;++j) {
   uintptr_t b=(uintptr_t)buffers[j];
   if(a<b+S3_PP_CHUNK && b<a+S3_PP_CHUNK) return S3_PP_INVALID;
  }
 }
 memset(p,0,sizeof(*p));atomic_init(&p->fault,0);
 for(unsigned i=0;i<4;++i)p->buffers[i]=buffers[i];
 for(unsigned i=0;i<3;++i)for(unsigned w=0;w<2;++w)atomic_init(&p->banks[i].jobs[w].state,IDLE);
 return S3_PP_OK;
}
int HOT s3_pp_accept(s3_parallel_pack *p,unsigned bank,const uint32_t *words,
 unsigned first,unsigned count,uint64_t sample,uint64_t now,uint64_t deadline) {
 if(!p) return S3_PP_INVALID;
 if(atomic_load_explicit(&p->fault,memory_order_relaxed))return S3_PP_FAULT;
 if(bank>=3 || !words || first>=S3_PP_WORDS || !count || count>S3_PP_WORDS ||
    sample>UINT64_MAX-count) return fail(p,S3_PP_INVALID);
 if(sample!=p->next_sample)return fail(p,S3_PP_SEQUENCE);
 if(deadline<=now)return fail(p,S3_PP_DEADLINE);
 if(p->banks[bank].owned || p->count==3)return S3_PP_BUSY;
 unsigned total=count+(unsigned)p->have_carry,pairs=total/2;
 uint64_t bytes=(uint64_t)pairs*5;
 if(p->reserved>UINT64_MAX-bytes)return fail(p,S3_PP_SEQUENCE);
 if(p->reserved-p->retired*S3_PP_CHUNK+bytes>4*S3_PP_CHUNK)return S3_PP_BUSY;
 s3_pp_bank *b=&p->banks[bank];
 b->words=words;b->sequence=p->bank_sequence++;b->deadline=deadline;
 b->output=p->reserved;b->first=first;b->pairs=pairs;
 b->prefix=p->carry;b->has_prefix=p->have_carry;b->owned=true;
 // Copy the unpaired last word before publishing jobs. It can survive reuse
 // of this bank, without any worker reading across into a later RF bank.
 p->have_carry=(total&1)!=0;
 if(p->have_carry)p->carry=words[(first+count-1)%S3_PP_WORDS]&0xfffff;
 unsigned cut=pairs/2;
 for(unsigned w=0;w<2;++w) {
  s3_pp_job *j=&b->jobs[w];j->begin=w?cut:0;j->end=w?pairs:cut;j->cursor=j->begin;
 }
 p->fifo[(p->head+p->count)%3]=bank;++p->count;
 p->next_sample+=count;p->reserved+=bytes;
 for(unsigned w=0;w<2;++w) {
  s3_pp_job *j=&b->jobs[w];
  atomic_store_explicit(&j->state,j->begin==j->end?DONE:READY,memory_order_release);
 }
 return S3_PP_OK;
}
static uint32_t HOT word(const s3_pp_bank *b,unsigned index) {
 if(b->has_prefix) { if(!index)return b->prefix;--index; }
 return b->words[(b->first+index)%S3_PP_WORDS]&0xfffff;
}
int HOT s3_pp_step(s3_parallel_pack *p,unsigned worker,unsigned max_pairs,
 uint64_t now,uint64_t bound,unsigned *processed) {
 if(!p || !processed)return S3_PP_INVALID;
 *processed=0;
 if(atomic_load_explicit(&p->fault,memory_order_relaxed))return S3_PP_FAULT;
 if(worker>1 || !max_pairs || !bound)return fail(p,S3_PP_INVALID);
 s3_pp_bank *b=NULL;
 for(unsigned i=0;i<3;++i) {
  s3_pp_bank *candidate=&p->banks[i];
  if(atomic_load_explicit(&candidate->jobs[worker].state,memory_order_acquire)==READY &&
     (!b || candidate->sequence<b->sequence))b=candidate;
 }
 if(!b)return S3_PP_EMPTY;
 if(now>=b->deadline || bound>=b->deadline-now)return fail(p,S3_PP_DEADLINE);
 s3_pp_job *j=&b->jobs[worker];unsigned n=j->end-j->cursor;
 if(n>max_pairs)n=max_pairs;
 unsigned i=0;
 while(i<n) {
  unsigned pair=j->cursor+i;
  uint64_t out=b->output+(uint64_t)pair*5;
  unsigned offset=(unsigned)(out%S3_PP_CHUNK),slot=(unsigned)((out/S3_PP_CHUNK)%4);
  unsigned logical=2*pair;
  unsigned input=(b->first+logical-(unsigned)b->has_prefix)%S3_PP_WORDS;
  if(n-i>=4 && (!b->has_prefix || logical) && input<=S3_PP_WORDS-8 &&
     !(offset&3) && offset<=S3_PP_CHUNK-20) {
   pack_eight(p->buffers[slot]+offset,b->words+input);i+=4;
  } else {
   uint32_t a=word(b,logical),c=word(b,logical+1);
   uint8_t bytes[5]={(uint8_t)a,(uint8_t)(a>>8),(uint8_t)((a>>16)|(c<<4)),
                     (uint8_t)(c>>4),(uint8_t)(c>>12)};
   for(unsigned k=0;k<5;++k) {
    uint64_t at=out+k;
    p->buffers[(at/S3_PP_CHUNK)%4][at%S3_PP_CHUNK]=bytes[k];
   }
   ++i;
  }
 }
 j->cursor+=n;*processed=n;
 if(j->cursor==j->end)atomic_store_explicit(&j->state,DONE,memory_order_release);
 return S3_PP_OK;
}
int HOT s3_pp_collect(s3_parallel_pack *p,uint64_t now) {
 if(!p)return S3_PP_INVALID;
 if(atomic_load_explicit(&p->fault,memory_order_relaxed))return S3_PP_FAULT;
 for(unsigned i=0;i<3;++i)if(p->banks[i].owned) {
  s3_pp_bank *b=&p->banks[i];
  for(unsigned w=0;w<2;++w)
   if(atomic_load_explicit(&b->jobs[w].state,memory_order_acquire)!=DONE && now>=b->deadline)
    return fail(p,S3_PP_DEADLINE);
 }
 while(p->count) {
  s3_pp_bank *b=&p->banks[p->fifo[p->head]];
  if(atomic_load_explicit(&b->jobs[0].state,memory_order_acquire)!=DONE ||
     atomic_load_explicit(&b->jobs[1].state,memory_order_acquire)!=DONE)break;
  p->published=b->output+(uint64_t)b->pairs*5;
  for(unsigned w=0;w<2;++w)atomic_store_explicit(&b->jobs[w].state,IDLE,memory_order_relaxed);
  b->owned=false;p->head=(p->head+1)%3;--p->count;
 }
 return S3_PP_OK;
}
int HOT s3_pp_reclaim(s3_parallel_pack *p,unsigned bank) {
 if(!p || bank>=3)return S3_PP_INVALID;
 if(atomic_load_explicit(&p->fault,memory_order_relaxed))return S3_PP_FAULT;
 return p->banks[bank].owned?S3_PP_BUSY:S3_PP_OK;
}
int HOT s3_pp_take(s3_parallel_pack *p,uint64_t *sequence,const uint8_t **payload) {
 if(!p || !sequence || !payload)return S3_PP_INVALID;
 if(atomic_load_explicit(&p->fault,memory_order_relaxed))return S3_PP_FAULT;
 if(p->submitted>=p->published/S3_PP_CHUNK)return S3_PP_EMPTY;
 unsigned slot=(unsigned)(p->submitted%4);
 if(p->dma_state[slot]!=DMA_FREE)return fail(p,S3_PP_INVALID);
 *sequence=p->submitted;*payload=p->buffers[slot];
 p->dma_sequence[slot]=p->submitted++;p->dma_state[slot]=DMA_ACTIVE;
 return S3_PP_OK;
}
int HOT s3_pp_complete(s3_parallel_pack *p,uint64_t sequence) {
 if(!p)return S3_PP_INVALID;
 // Even after a fault, reap can retire DMA; never let failure free active DMA.
 unsigned slot=(unsigned)(sequence%4);
 if(sequence<p->retired || sequence>=p->submitted || p->dma_sequence[slot]!=sequence ||
    p->dma_state[slot]!=DMA_ACTIVE)return S3_PP_STALE;
 p->dma_state[slot]=DMA_DONE;
 while(p->retired<p->submitted && p->dma_state[p->retired%4]==DMA_DONE) {
  p->dma_state[p->retired%4]=DMA_FREE;++p->retired;
 }
 return S3_PP_OK;
}

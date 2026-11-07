#include "tpre_runtime.h"
#include <limits.h>
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#define HOT IRAM_ATTR
#else
#define HOT
#endif

static int HOT __attribute__((noinline)) tpre_fail(tpre_runtime *r, unsigned reason) {
    atomic_store_explicit(&r->fault,reason,memory_order_relaxed);
    atomic_store_explicit(&r->stop,1,memory_order_release);
    return TPRE_ERROR;
}
void HOT tpre_request_stop(tpre_runtime *r) {
    if(r)atomic_store_explicit(&r->stop,1,memory_order_release);
}
bool HOT tpre_stopping(const tpre_runtime *r) {
    return !r || atomic_load_explicit(&r->stop,memory_order_acquire)!=0;
}
size_t tpre_size(void) { return sizeof(tpre_runtime); }
bool tpre_init(tpre_runtime *r,hbpipe *p,hbnative *n,s3_native_capture *c,
              uint8_t *const frames[TPRE_FRAMES],unsigned epoch,
              s3_native_clock clock,void *clock_ctx,uint32_t error,
              uint32_t bound,tpre_io io) {
    if(!r||!p||!n||!c||c->running||!frames||!epoch||epoch>UINT16_MAX||
       !clock||!bound||error>=bound||!io.submit||!io.reap||!io.feed||
       p->produce_next||p->consume_next||p->reap_next||n->pipe!=p||
       n->epoch!=epoch||n->fault||n->count||n->fill||n->consumed_samples)return false;
    for(unsigned i=0;i<TPRE_FRAMES;i++) {
        if(!frames[i]||((uintptr_t)frames[i]&15u)||
           (uintptr_t)frames[i]>UINTPTR_MAX-TPRE_FRAME_BYTES)return false;
        for(unsigned j=0;j<i;j++)
            if((uintptr_t)frames[i]<(uintptr_t)frames[j]+TPRE_FRAME_BYTES&&
               (uintptr_t)frames[j]<(uintptr_t)frames[i]+TPRE_FRAME_BYTES)return false;
    }
    memset(r,0,sizeof(*r));
    r->pipeline=p;r->native=n;r->capture=c;r->epoch=epoch;
    r->clock=clock;r->clock_ctx=clock_ctx;r->clock_error=error;r->step_bound=bound;r->io=io;
    for(unsigned i=0;i<TPRE_FRAMES;i++)r->frames[i].data=frames[i];
    atomic_init(&r->stop,0);atomic_init(&r->fault,0);
    return true;
}
static int HOT __attribute__((noinline)) tpre_poll(tpre_runtime *r,tpre_event *e) {
    unsigned budget=r->prepare_words>1024?1024:r->prepare_words;
    unsigned before=budget;
    bool ok=s3_native_poll_budget(r->capture,&budget);
    e->words=before-budget;r->prepare_words-=e->words;
    if(!ok)return tpre_fail(r,1);
    return TPRE_OK;
}
static int HOT __attribute__((noinline)) tpre_reap(tpre_runtime *r,tpre_event *e) {
    int16_t *output=NULL;uint32_t sequence=0;
    int rc=hbpipe_reap(r->pipeline,&output,&sequence);
    if(rc==HBPIPE_EMPTY)return TPRE_IDLE;
    if(rc!=HBPIPE_OK||sequence!=r->block_reap)return tpre_fail(r,2);
    unsigned slot=(sequence/TPRE_BLOCKS_PER_FRAME)&(TPRE_FRAMES-1);
    unsigned block=sequence%TPRE_BLOCKS_PER_FRAME;
    tpre_frame *f=&r->frames[slot];
    if(f->state!=TPRE_FILLING||f->sequence!=sequence/TPRE_BLOCKS_PER_FRAME||
       f->completed!=block||f->reserved<=block||
       (uint8_t*)output!=f->data+block*TPRE_BLOCK_BYTES)return tpre_fail(r,3);
    ++f->completed;++r->block_reap;e->sequence=sequence;
    if(f->completed==TPRE_BLOCKS_PER_FRAME)f->state=TPRE_READY;
    return TPRE_OK;
}
static int HOT __attribute__((noinline)) tpre_produce(tpre_runtime *r,tpre_event *e) {
    uint32_t sequence=r->block_next;
    uint32_t frame_seq=sequence/TPRE_BLOCKS_PER_FRAME;
    if(frame_seq>UINT32_MAX/TPRE_FRAME_BYTES)return tpre_fail(r,4);
    unsigned slot=frame_seq&(TPRE_FRAMES-1),block=sequence%TPRE_BLOCKS_PER_FRAME;
    tpre_frame *f=&r->frames[slot];
    int16_t *output=NULL;
    if((!block&&f->state==TPRE_FREE)||
       (block&&f->state==TPRE_FILLING&&f->sequence==frame_seq&&f->reserved==block))
        output=(int16_t*)(f->data+block*TPRE_BLOCK_BYTES);
    hbnative_result result={0};
    int rc=hbnative_step_clocked(r->native,output,HBPIPE_RAW,r->clock,r->clock_ctx,
                                r->clock_error,r->step_bound,&result);
    e->words=result.consumed;e->copied=result.copied;e->produced=result.produced;
    e->sequence=result.sequence;e->first_sample=result.first_sample;
    if(result.produced) {
        if(!output||result.sequence!=sequence)return tpre_fail(r,6);
        if(!block) {f->state=TPRE_FILLING;f->sequence=frame_seq;f->reserved=0;f->completed=0;}
        ++f->reserved;++r->block_next;
    }
    if(rc!=HBNATIVE_OK&&rc!=HBNATIVE_EMPTY&&rc!=HBNATIVE_BUSY&&
       rc!=HBNATIVE_NEED_OUTPUT)return tpre_fail(r,5);
    return result.consumed||result.produced?TPRE_OK:TPRE_IDLE;
}
static int HOT __attribute__((noinline)) tpre_dma_reap(tpre_runtime *r,tpre_event *e) {
    if(!r->dma_count)return TPRE_IDLE;
    uint32_t sequence=UINT32_MAX;
    int rc=r->io.reap(r->io.ctx,&sequence);
    if(rc==TPRE_IDLE)return TPRE_IDLE;
    if(rc!=TPRE_OK||sequence!=r->complete_next)return tpre_fail(r,7);
    tpre_frame *f=&r->frames[sequence&(TPRE_FRAMES-1)];
    if(f->state!=TPRE_DMA||f->sequence!=sequence)return tpre_fail(r,8);
    f->state=TPRE_FREE;f->reserved=f->completed=0;
    ++r->complete_next;--r->dma_count;e->sequence=sequence;return TPRE_OK;
}
static int HOT __attribute__((noinline)) tpre_dma_submit(tpre_runtime *r,tpre_event *e) {
    if(r->dma_count==TPRE_QUEUE_DEPTH)return TPRE_IDLE;
    uint32_t sequence=r->submit_next;
    tpre_frame *f=&r->frames[sequence&(TPRE_FRAMES-1)];
    if(f->state!=TPRE_READY)return TPRE_IDLE;
    if(f->sequence!=sequence||f->completed!=TPRE_BLOCKS_PER_FRAME||
       f->reserved!=TPRE_BLOCKS_PER_FRAME)return tpre_fail(r,9);
    /* Retain ownership even if queue_trans reports an unexpected error. */
    f->state=TPRE_DMA;++r->dma_count;++r->submit_next;e->sequence=sequence;
    if(r->io.submit(r->io.ctx,r->epoch,sequence,f->data,TPRE_FRAME_BYTES)!=TPRE_OK)
        return tpre_fail(r,10);
    return TPRE_OK;
}
int HOT tpre_owner_step(tpre_runtime *r,tpre_event *e) {
    if(!e)return TPRE_ERROR;
    *e=(tpre_event){0};
    if(tpre_stopping(r)){e->operation=TPRE_OP_STOP;e->result=TPRE_ERROR;return TPRE_ERROR;}
    unsigned phase=r->phase;e->phase=phase;int result=TPRE_ERROR;
    switch(phase) {
    case 0:r->prepare_words=TPRE_PREPARE_WORDS_PER_ITERATION;
        /* fall through */
    case 3:case 5:case 7:e->operation=TPRE_OP_POLL;result=tpre_poll(r,e);break;
    case 1:e->operation=TPRE_OP_REAP;result=tpre_reap(r,e);break;
    case 2:e->operation=TPRE_OP_PRODUCE;result=tpre_produce(r,e);break;
    case 4:e->operation=TPRE_OP_DMA_REAP;result=tpre_dma_reap(r,e);break;
    case 6:e->operation=TPRE_OP_DMA_SUBMIT;result=tpre_dma_submit(r,e);break;
    case 8:e->operation=TPRE_OP_FEED;result=r->io.feed(r->io.ctx,0)?TPRE_OK:tpre_fail(r,11);break;
    default:result=tpre_fail(r,12);break;
    }
    if(result!=TPRE_ERROR)r->phase=(phase+1)%TPRE_PHASES;
    e->result=result;return result;
}
int HOT tpre_worker_step(tpre_runtime *r,tpre_event *e) {
    if(!e)return TPRE_ERROR;
    *e=(tpre_event){.operation=TPRE_OP_WORK};
    if(tpre_stopping(r)){e->result=TPRE_ERROR;return TPRE_ERROR;}
    int rc=hbpipe_work(r->pipeline);
    if(rc!=HBPIPE_OK&&rc!=HBPIPE_EMPTY){e->result=tpre_fail(r,13);return TPRE_ERROR;}
    if(rc==HBPIPE_OK){e->produced=1;e->sequence=r->pipeline->consume_next-1;}
    if(!r->io.feed(r->io.ctx,1)){e->result=tpre_fail(r,14);return TPRE_ERROR;}
    e->result=rc==HBPIPE_OK?TPRE_OK:TPRE_IDLE;return e->result;
}

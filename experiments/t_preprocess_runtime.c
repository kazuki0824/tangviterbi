/* Fresh reconstruction, 2026-11-05. The recovered target C executes in two
 * coroutines. Only generated copies contain instrumentation. Virtual cycles
 * are supplied fees; no host elapsed time is used as ESP32 timing evidence. */
#define _XOPEN_SOURCE 700
#include "tpre_model_costs.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ucontext.h>

enum { CTRL=0x60033d5c, INDEX=0x60033d60, SELECT=0x600c101c, WORDS=16384 };
/* MODE_QIO alone widens data, not the 16-bit command or 64-bit address. */
enum { WIRE_CYCLES=(TPRE_FRAME_BYTES*8/4+16+64)*3 };
static _Alignas(16) uint32_t raw[3][WORDS];
static _Alignas(16) uint8_t payload[TPRE_FRAMES][TPRE_FRAME_BYTES+16];
static hbpipe pipeline;
static hbnative adapter;
static s3_native_capture capture;
static tpre_runtime runtime;
static uint64_t now, ready[2], rf_samples, rf_phase, stop_cycle, ack_cycle;
static uint64_t ledger[2][MODEL_CATEGORIES], events[2][MODEL_CATEGORIES];
static uint64_t stalls[2], idle_cycles[2], stop_charge[2], stop_stall[2];
static uint64_t next_tick=2400000, next_phy=240000, phy_busy_until;
static uint64_t core0_irq_service_until;
static unsigned rf_on, selected, rf_index, core, started, stopped[2];
static unsigned requested_banks=100, stall_percent, phy_cycles, bound=20000, clock_error;
static unsigned destroy_source=1, outcome, inject, injected, fail_phase;
static uint64_t first_accept_cycle, last_accept_cycle, first_accept_charge[2], last_accept_charge[2];
static uint64_t first_accept_blocks, last_accept_blocks, accepted_words;
static uint64_t accepted_at[3], released_banks, copied_words, copy_segments, copy_wraps;
static uint64_t checked_blocks, raw_words_checked, destroyed_banks;
static uint64_t phase_calls[9], worker_calls, poll_calls, last_poll, max_poll_gap;
static uint64_t max_step_cycles, max_worker_cycles, max_phase_cycles, max_source_hold;
static unsigned phase_expected, max_dma_count, max_owned_banks;
static unsigned previous_copy_end, previous_copy_bank=3;
static ucontext_t scheduler, contexts[2];
static char stacks[2][262144];
static uint64_t admission_remaining, admission_sampled, failure_deadline, failure_time;
static uint64_t failure_pending_raw, failure_step_base, failure_copy_words, failure_consumed_words;
static uint64_t failure_release_base=UINT64_MAX;
static unsigned admission_bank, failure_pipeline_status[2], failure_fill, failure_path;
static unsigned failure_copy_chunks, failure_would_produce;

enum { Q_FREE, Q_QUEUED, Q_WIRE, Q_DONE };
typedef struct {
    const uint8_t *data; uint32_t sequence; uint64_t hash; unsigned state;
} transaction;
static transaction queue[2];
static unsigned qhead, qcount, launch_count, irq_kind, irq_slot, irq_chain, active_slot=2;
static uint64_t spi_event=UINT64_MAX, wire_done=UINT64_MAX, irq_end=UINT64_MAX;
static uint64_t wire_completions, dma_reaps, spi_starts;
static uint64_t wire_started_at, wire_intervals, wire_min=UINT64_MAX, wire_max;
typedef struct {
    uint64_t cycles, accepted, consumed, charged[2];
    unsigned block_next, block_reap, owned, bank;
} bank_observation;
static bank_observation bank_observations[256];
static unsigned bank_observation_count;

static uint64_t total_charge(unsigned c) {
    uint64_t n=0;for(unsigned k=0;k<MODEL_CATEGORIES;k++)n+=ledger[c][k];return n;
}
static void broken(unsigned code) {if(!outcome)outcome=code;}
static uint32_t sample_word(uint64_t n) {
    uint32_t i=(73*n+(n>>3))&1023, q=(131*n+17)&1023;
    uint32_t w=i|(q<<10)|(((n*317+0xa55)&4095)<<20);
    /* This test's ideal RF ABI excludes a payload equal to the sentinel. */
    return w==UINT32_C(0xa5c33c5a)?w^UINT32_C(0x10000000):w;
}
static int signed10(uint32_t word) {int n=word&1023;return n&512?n-1024:n;}
static int16_t oracle(uint64_t output,unsigned component) {
    /* Independently pinned direct 31-tap convolution; never calls the kernel. */
    static const int h[31]={-18,0,68,0,-182,0,404,0,-803,0,1533,0,-3116,0,10305,16384,10305,0,-3116,0,1533,0,-803,0,404,0,-182,0,68,0,-18};
    uint64_t n=2*output;int64_t sum=0;
    for(unsigned t=0;t<31;t++)if(n>=t)sum+=(int64_t)h[t]*signed10(sample_word(n-t)>>(10*component));
    int64_t divisor=INT64_C(1)<<pipeline.shift;
    int64_t value=sum>=0?sum/divisor:-((-sum+divisor-1)/divisor);
    return value>32767?32767:value< -32768?-32768:(int16_t)value;
}
static uint64_t fingerprint(const void *data,unsigned bytes) {
    const uint8_t *p=data;uint64_t h=UINT64_C(1469598103934665603);
    for(unsigned n=0;n<bytes;n++)h=(h^p[n])*UINT64_C(1099511628211);
    return h;
}
static void validate_guards(void) {
    for(unsigned f=0;f<TPRE_FRAMES;f++)for(unsigned n=TPRE_FRAME_BYTES;n<sizeof(payload[f]);n++)
        if(payload[f][n]!=0xa5)broken(90);
}
static void validate_dma(void) {
    for(unsigned n=0;n<2;n++)if(queue[n].state!=Q_FREE)
        if(fingerprint(queue[n].data,TPRE_FRAME_BYTES)!=queue[n].hash)broken(91);
    validate_guards();
}
static void advance(uint64_t target) {
    assert(target>=now);
    if(rf_on) {
        rf_phase+=target-now;
        while(rf_phase>=15) {
            rf_phase-=15;
            for(unsigned b=0;b<3;b++)if(selected&(1u<<b)) {
                if(adapter.banks[b].owned)broken(92);
                raw[b][rf_index]=sample_word(rf_samples);
            }
            ++rf_samples;rf_index=(rf_index+1)&(WORDS-1);
        }
    }
    now=target;
}
void model_charge(unsigned category,uint64_t cycles) {
    assert(category<MODEL_CATEGORIES);
    if(!started||!cycles)return;
    ledger[core][category]+=cycles;events[core][category]++;
    uint64_t extra=(cycles*stall_percent+99)/100;stalls[core]+=extra;
    ready[core]=now+cycles+extra;
    swapcontext(&contexts[core],&scheduler);
}
static void interrupt_charge(unsigned c,unsigned category,uint64_t cycles) {
    ledger[c][category]+=cycles;events[c][category]++;
    if(ready[c]<now){idle_cycles[c]+=now-ready[c];ready[c]=now;}
    ready[c]+=cycles;
    /* SPI is level1. A pending core0 tick delays the handler's service end,
     * not just the owner task. Equal-time events choose tick first. */
    if(c==0&&(category==M_SPI_IRQ||category==M_TICK))
        core0_irq_service_until=(core0_irq_service_until>now?core0_irq_service_until:now)+cycles;
    if(c==1&&category!=M_PHY&&phy_busy_until>now)phy_busy_until+=cycles;
}
uint64_t model_clock(void *ctx) {
    (void)ctx;model_charge(M_CLOCK,COST_CLOCK);
    if(inject==6&&started&&core==0&&runtime.block_next>=4){injected=1;return UINT64_MAX;}
    return now+clock_error;
}
static uint32_t rd(void *ctx,uint32_t address) {
    (void)ctx;return address==INDEX?rf_index:address==SELECT?selected:0;
}
static void wr(void *ctx,uint32_t address,uint32_t value) {
    (void)ctx;if(address==CTRL)rf_on=value>>31;if(address==SELECT)selected=value&15;
}
static uint32_t *bank_pointer(void *ctx,unsigned b){(void)ctx;assert(b<3);return raw[b];}
void model_poll(void) {
    if(last_poll&&now-last_poll>max_poll_gap)max_poll_gap=now-last_poll;
    last_poll=now;poll_calls++;
}
void model_fill(unsigned bank,unsigned at,unsigned count) {
    if(started&&(adapter.banks[bank].owned||(rf_on&&(selected&(1u<<bank)))))broken(93);
    model_charge(M_FILL,model_fill_fee(at,count));
    if(started&&adapter.banks[bank].owned)broken(93);
}
void model_accept(hbnative *a,unsigned bank) {
    hbnative_bank *source=&a->banks[bank];
    if(source->first_sample!=accepted_words)broken(94);
    for(unsigned n=0;n<source->count;n++) {
        if(source->words[(source->first+n)&(WORDS-1)]!=sample_word(source->first_sample+n))broken(95);
        raw_words_checked++;
    }
    accepted_words+=source->count;accepted_at[bank]=now;
    if(!first_accept_cycle) {
        first_accept_cycle=now;first_accept_blocks=runtime.block_next;
        for(unsigned c=0;c<2;c++)first_accept_charge[c]=total_charge(c);
    }
    last_accept_cycle=now;last_accept_blocks=runtime.block_next;
    for(unsigned c=0;c<2;c++)last_accept_charge[c]=total_charge(c);
    if(a->count>max_owned_banks)max_owned_banks=a->count;
    if(bank_observation_count<256) {
        bank_observation *v=&bank_observations[bank_observation_count++];
        *v=(bank_observation){now,accepted_words,a->consumed_samples,{total_charge(0),total_charge(1)},runtime.block_next,runtime.block_reap,a->count,bank};
    }
}
void model_release(hbnative *a,unsigned bank) {
    if(!a->banks[bank].owned||a->banks[bank].consumed!=a->banks[bank].count)broken(96);
    uint64_t age=now-accepted_at[bank];if(age>max_source_hold)max_source_hold=age;
    released_banks++;
    if(destroy_source){memset(raw[bank],0x5a,sizeof(raw[bank]));destroyed_banks++;}
}
void model_copy(const uint32_t *source,unsigned count) {
    model_charge(M_COPY,model_copy_fee(count));
    unsigned found=3,at=0;
    for(unsigned b=0;b<3;b++) {
        uintptr_t address=(uintptr_t)source,begin=(uintptr_t)raw[b];
        if(address>=begin&&address<begin+sizeof(raw[b])){found=b;at=(address-begin)/4;break;}
    }
    if(found==3||!adapter.banks[found].owned||at+count>WORDS)broken(97);
    if(found==previous_copy_bank&&at==0&&previous_copy_end==WORDS)copy_wraps++;
    previous_copy_bank=found;previous_copy_end=at+count;
    for(unsigned n=0;n<count;n++)if(source[n]!=sample_word(adapter.consumed_samples+n))broken(98);
    copied_words+=count;copy_segments++;
}
void model_producer_input(hbpipe *p,const uint32_t *source,int16_t *output) {
    if(inject==8&&!injected&&p->produce_next>=2){((uint32_t*)source)[0]^=1;injected=1;}
    for(unsigned n=0;n<HBPIPE_RAW;n++)if(source[n]!=sample_word((uint64_t)p->produce_next*HBPIPE_RAW+n))broken(99);
    for(unsigned n=0;n<2;n++)if(queue[n].state!=Q_FREE&&
        (uintptr_t)output>=(uintptr_t)queue[n].data&&
        (uintptr_t)output<(uintptr_t)queue[n].data+TPRE_FRAME_BYTES)broken(100);
}
void model_worker_before(hbpipe_slot *slot) {
    if(inject==9&&!injected&&slot->sequence>=2){slot->sequence++;injected=1;}
}
void model_done(hbpipe_slot *slot) {
    for(unsigned n=0;n<HBPIPE_OUTPUT;n++)for(unsigned c=0;c<2;c++)
        if(slot->output[2*n+c]!=oracle((uint64_t)slot->sequence*HBPIPE_OUTPUT+n,c))broken(101);
    checked_blocks++;validate_dma();
}
void model_admission(hbnative *a,unsigned bank,uint64_t sampled) {
    failure_time=now;admission_sampled=sampled;admission_bank=bank;
    failure_deadline=a->banks[bank].deadline;
    admission_remaining=failure_deadline>sampled?failure_deadline-sampled:0;
    failure_fill=a->fill;failure_pending_raw=a->next_sample-a->consumed_samples;
    for(unsigned s=0;s<2;s++)failure_pipeline_status[s]=hbpipe_status(a->pipe,s);
    unsigned next=a->pipe->produce_next&1,have=a->fill,direct=0;
    /* Counterfactual BASE fees omit the guard, stalls and interrupts. This
     * is not an admissible target bound or an execution-time lower bound. */
    uint64_t fee=model_clocked_fees[a->count]+((a->count||a->fill)?COST_ADAPTER_STEP_ACTIVE:COST_ADAPTER_STEP_IDLE);
    if(!have&&a->count) {
        hbnative_bank *s=&a->banks[a->fifo[a->head]];
        unsigned at=(s->first+s->consumed)&(WORDS-1);
        direct=s->count-s->consumed>=HBPIPE_RAW&&WORDS-at>=HBPIPE_RAW;
    }
    failure_path=failure_pipeline_status[next]!=HBPIPE_FREE?1:direct?2:(a->fill||a->count)?3:4;
    if(direct)have=HBPIPE_RAW;
    else for(unsigned k=0;k<a->count&&have<HBPIPE_RAW;k++) {
        unsigned source_bank=a->fifo[(a->head+k)%3];
        hbnative_bank *s=&a->banks[source_bank];
        unsigned at=(s->first+s->consumed)&(WORDS-1),remaining=s->count-s->consumed;
        while(remaining&&have<HBPIPE_RAW) {
            unsigned n=remaining;if(n>WORDS-at)n=WORDS-at;if(n>HBPIPE_RAW-have)n=HBPIPE_RAW-have;
            fee+=COST_ADAPTER_STEP_PER_COPY_CHUNK+model_copy_fee(n)+COST_ADAPTER_ADVANCE;
            have+=n;remaining-=n;at=(at+n)&(WORDS-1);failure_copy_words+=n;failure_copy_chunks++;
            if(!remaining&&source_bank==bank)failure_release_base=fee;
        }
    }
    if(have==HBPIPE_RAW) {
        fee+=COST_ADAPTER_PUBLISH;
        unsigned sequence=runtime.block_next,frame_sequence=sequence/TPRE_BLOCKS_PER_FRAME;
        unsigned block=sequence%TPRE_BLOCKS_PER_FRAME;
        tpre_frame *f=&runtime.frames[frame_sequence&(TPRE_FRAMES-1)];
        bool output=(!block&&f->state==TPRE_FREE)||(block&&f->state==TPRE_FILLING&&f->sequence==frame_sequence&&f->reserved==block);
        if(!output)failure_path=5;
        else if(failure_pipeline_status[next]!=HBPIPE_FREE)fee+=COST_HB_BUSY;
        else {
            fee+=COST_HB_PRODUCE;failure_would_produce=1;
            if(direct) {
                fee+=COST_ADAPTER_ADVANCE;
                hbnative_bank *s=&a->banks[a->fifo[a->head]];
                if(a->fifo[a->head]==bank&&s->count-s->consumed==HBPIPE_RAW)failure_release_base=fee;
            }
        }
    }
    failure_step_base=fee+COST_ADAPTER_READ_CLOCK+COST_CLOCK;
    failure_consumed_words=direct?(failure_would_produce?HBPIPE_RAW:0):failure_copy_words;
}
void model_step_interval(uint64_t cycles){if(cycles>max_step_cycles)max_step_cycles=cycles;}

static int next_queued(void) {
    for(unsigned offset=0;offset<qcount;offset++) {
        unsigned n=(qhead+offset)&1;if(queue[n].state==Q_QUEUED)return (int)n;
    }
    return -1;
}
static int submit(void *ctx,unsigned epoch,uint32_t sequence,const void *data,unsigned bytes) {
    (void)ctx;model_charge(M_SPI_SUBMIT,COST_SPI_SUBMIT);
    if(inject==1&&!injected){injected=1;return TPRE_ERROR;}
    if(epoch!=1||bytes!=TPRE_FRAME_BYTES||qcount>=2||sequence!=dma_reaps+qcount){broken(102);return TPRE_ERROR;}
    unsigned n=(qhead+qcount)&1;
    if(queue[n].state!=Q_FREE)broken(103);
    for(unsigned k=0;k<TPRE_FRAME_BYTES/4;k++)for(unsigned c=0;c<2;c++)
        if(((const int16_t*)data)[2*k+c]!=oracle((uint64_t)sequence*(TPRE_FRAME_BYTES/4)+k,c))broken(104);
    queue[n]=(transaction){data,sequence,fingerprint(data,bytes),Q_QUEUED};qcount++;
    if(qcount>max_dma_count)max_dma_count=qcount;
    if(active_slot==2&&spi_event==UINT64_MAX&&irq_end==UINT64_MAX)spi_event=now;
    return TPRE_OK;
}
static int reap(void *ctx,uint32_t *sequence) {
    (void)ctx;
    if(!qcount||queue[qhead].state!=Q_DONE){model_charge(M_SPI_REAP_EMPTY,COST_SPI_REAP_EMPTY);return TPRE_IDLE;}
    model_charge(M_SPI_REAP_DONE,COST_SPI_REAP_DONE);validate_dma();
    if(inject==2&&!injected){injected=1;*sequence=queue[qhead].sequence+1;return TPRE_OK;}
    *sequence=queue[qhead].sequence;queue[qhead].state=Q_FREE;
    qhead=(qhead+1)&1;qcount--;dma_reaps++;return TPRE_OK;
}
static bool feed(void *ctx,unsigned c) {
    static uint64_t next_feed[2]={600000000,600000000};
    (void)ctx;model_charge(M_FEED,COST_FEED);
    if(now>=next_feed[c]){model_charge(M_WDT,COST_WDT_EXTRA);next_feed[c]=now+600000000;}
    if((inject==3&&c==0)||(inject==4&&c==1))if(capture.unit&&!injected){injected=1;return false;}
    return true;
}
static void snapshot_stop(void) {
    if(stop_cycle)return;
    stop_cycle=now;
    for(unsigned c=0;c<2;c++){stop_charge[c]=total_charge(c);stop_stall[c]=stalls[c];}
    fail_phase=runtime.phase;tpre_request_stop(&runtime);s3_native_stop(&capture);
}
static void task0(void) {
    while(!tpre_stopping(&runtime)&&!outcome&&capture.unit<requested_banks) {
        unsigned phase=runtime.phase;uint64_t begin=now;
        if(phase!=phase_expected)broken(105);
        model_charge(M_OWNER,model_owner_fees[phase]);
        tpre_event event;int rc=tpre_owner_step(&runtime,&event);
        if(event.phase!=phase||event.operation==TPRE_OP_STOP)if(!tpre_stopping(&runtime))broken(106);
        phase_calls[phase]++;
        if(rc!=TPRE_ERROR)phase_expected=(phase+1)%TPRE_PHASES;
        if(now-begin>max_phase_cycles)max_phase_cycles=now-begin;
        if(runtime.dma_count>2||adapter.count>3)broken(107);
        validate_guards();
    }
    snapshot_stop();stopped[0]=1;swapcontext(&contexts[0],&scheduler);abort();
}
static void task1(void) {
    while(!tpre_stopping(&runtime)&&!outcome) {
        uint64_t begin=now;model_charge(M_WORKER,COST_WORKER);worker_calls++;
        tpre_event event;tpre_worker_step(&runtime,&event);
        if(now-begin>max_worker_cycles)max_worker_cycles=now-begin;
    }
    stopped[1]=1;ack_cycle=now;swapcontext(&contexts[1],&scheduler);abort();
}
static void spi_interrupt(void) {
    if(now==spi_event) {
        spi_event=UINT64_MAX;int next=next_queued();if(next<0){broken(108);return;}
        irq_slot=(unsigned)next;irq_kind=1;irq_chain=0;
        uint64_t fee=launch_count++?COST_IRQ_START:COST_IRQ_FIRST;
        interrupt_charge(0,M_SPI_IRQ,fee);irq_end=core0_irq_service_until;
    } else if(now==wire_done) {
        wire_done=UINT64_MAX;if(active_slot>=2){broken(109);return;}
        uint64_t interval=now-wire_started_at;wire_intervals++;
        if(interval<wire_min)wire_min=interval;
        if(interval>wire_max)wire_max=interval;
        irq_slot=active_slot;irq_kind=2;irq_chain=next_queued()>=0;
        uint64_t fee=irq_chain?COST_IRQ_CHAIN:COST_IRQ_COMPLETE;
        interrupt_charge(0,M_SPI_IRQ,fee);irq_end=core0_irq_service_until;
    } else if(now==irq_end) {
        irq_end=UINT64_MAX;
        if(irq_kind==2) {
            if(inject==7&&!injected){((uint8_t*)queue[irq_slot].data)[0]^=1;injected=1;}
            validate_dma();queue[irq_slot].state=Q_DONE;wire_completions++;active_slot=2;
        }
        int next=irq_kind==1?(int)irq_slot:irq_chain?next_queued():-1;
        if(next>=0) {
            active_slot=(unsigned)next;queue[next].state=Q_WIRE;spi_starts++;
            wire_started_at=now;
            wire_done=now+WIRE_CYCLES;
        }
    }
}
static void initialize(void) {
    memset(&pipeline,0,sizeof(pipeline));memset(&adapter,0,sizeof(adapter));
    memset(&capture,0,sizeof(capture));memset(&runtime,0,sizeof(runtime));
    memset(payload,0xa5,sizeof(payload));
    uint8_t *frames[TPRE_FRAMES];for(unsigned n=0;n<TPRE_FRAMES;n++)frames[n]=payload[n];
    assert(hbpipe_init(&pipeline,10)==HBPIPE_OK);
    assert(hbnative_init(&adapter,&pipeline,1)==HBNATIVE_OK);
    assert(tpre_init(&runtime,&pipeline,&adapter,&capture,frames,1,model_clock,NULL,clock_error,bound,(tpre_io){NULL,submit,reap,feed}));
}
static int selftest(void) {
    initialize();unsigned passed=0,failed=0;
    uint8_t *frames[TPRE_FRAMES];for(unsigned n=0;n<TPRE_FRAMES;n++)frames[n]=payload[n];
    tpre_io io={NULL,submit,reap,feed};
#define CHECK(expr) do{if(expr)passed++;else failed++;}while(0)
    CHECK(!tpre_init(NULL,&pipeline,&adapter,&capture,frames,1,model_clock,NULL,0,bound,io));
    CHECK(!tpre_init(&runtime,&pipeline,&adapter,&capture,frames,0,model_clock,NULL,0,bound,io));
    CHECK(!tpre_init(&runtime,&pipeline,&adapter,&capture,frames,2,model_clock,NULL,0,bound,io));
    CHECK(!tpre_init(&runtime,&pipeline,&adapter,&capture,frames,1,NULL,NULL,0,bound,io));
    CHECK(!tpre_init(&runtime,&pipeline,&adapter,&capture,frames,1,model_clock,NULL,bound,bound,io));
    CHECK(!tpre_init(&runtime,&pipeline,&adapter,&capture,frames,1,model_clock,NULL,0,0,io));
    frames[1]=frames[0];CHECK(!tpre_init(&runtime,&pipeline,&adapter,&capture,frames,1,model_clock,NULL,0,bound,io));
    frames[1]=frames[0]+16;CHECK(!tpre_init(&runtime,&pipeline,&adapter,&capture,frames,1,model_clock,NULL,0,bound,io));
    frames[1]=payload[1]+1;CHECK(!tpre_init(&runtime,&pipeline,&adapter,&capture,frames,1,model_clock,NULL,0,bound,io));
    frames[1]=NULL;CHECK(!tpre_init(&runtime,&pipeline,&adapter,&capture,frames,1,model_clock,NULL,0,bound,io));
    frames[1]=payload[1];capture.running=true;
    CHECK(!tpre_init(&runtime,&pipeline,&adapter,&capture,frames,1,model_clock,NULL,0,bound,io));
    capture.running=false;io.submit=NULL;
    CHECK(!tpre_init(&runtime,&pipeline,&adapter,&capture,frames,1,model_clock,NULL,0,bound,io));
    initialize();runtime.phase=9;tpre_event e;
    CHECK(tpre_owner_step(&runtime,&e)==TPRE_ERROR&&atomic_load(&runtime.fault)==12&&tpre_stopping(&runtime));
    initialize();pipeline.slots[0].sequence=1;atomic_store(&pipeline.slots[0].status,HBPIPE_READY);
    CHECK(tpre_worker_step(&runtime,&e)==TPRE_ERROR&&atomic_load(&runtime.fault)==13);
    initialize();tpre_request_stop(&runtime);
    CHECK(tpre_owner_step(&runtime,&e)==TPRE_ERROR&&e.operation==TPRE_OP_STOP);
    CHECK(tpre_worker_step(&runtime,&e)==TPRE_ERROR);
    printf("{\"executed\":%u,\"passed\":%u,\"failed\":%u,\"non_fail_fast\":true}\n",passed+failed,passed,failed);
    return failed?1:0;
}

static void report(uint64_t first_phy_cycle) {
    unsigned owned=0,states[4]={0};
    for(unsigned b=0;b<3;b++)owned+=adapter.banks[b].owned;
    for(unsigned f=0;f<TPRE_FRAMES;f++)states[runtime.frames[f].state]++;
    printf("{\"requested_banks\":%u,\"banks\":%u,\"cycles_at_owner_stop\":%"PRIu64",\"cycles_at_worker_ack\":%"PRIu64",\"observed_until_cycles\":%"PRIu64",",requested_banks,capture.unit,stop_cycle,ack_cycle,now);
    printf("\"native_fault\":%u,\"adapter_fault\":%u,\"task_fault\":%u,\"outcome\":%u,\"injection\":%u,\"injection_executed\":%s,\"stopped\":[%u,%u],\"rf_stopped\":%s,",capture.fault,adapter.fault,atomic_load(&runtime.fault),outcome,inject,injected?"true":"false",stopped[0],stopped[1],rf_on?"false":"true");
    printf("\"prepare_per_iteration\":%u,\"prepare_per_poll\":1024,\"declared_step_bound\":%u,\"stall_percent\":%u,\"clock_error\":%u,\"phy_duration_cycles\":%u,\"phy_period_ms\":1000,\"phy_core\":1,\"phy_first_cycle\":%"PRIu64",\"phase_at_stop\":%u,",TPRE_PREPARE_WORDS_PER_ITERATION,bound,stall_percent,clock_error,phy_cycles,first_phy_cycle,fail_phase);
    printf("\"wire_cycles_per_frame\":%u,",(unsigned)WIRE_CYCLES);
    printf("\"wire_intervals_observed\":%"PRIu64",\"wire_interval_min_cycles\":%"PRIu64",\"wire_interval_max_cycles\":%"PRIu64",",wire_intervals,wire_intervals?wire_min:0,wire_max);
    printf("\"rf_samples\":%"PRIu64",\"accepted_words\":%"PRIu64",\"consumed_words\":%"PRIu64",\"produced_words\":%"PRIu64",\"carry_words\":%u,\"retained_source_banks\":%u,\"released_banks\":%"PRIu64",\"destroyed_banks\":%"PRIu64",",rf_samples,accepted_words,adapter.consumed_samples,adapter.produced_samples,adapter.fill,owned,released_banks,destroyed_banks);
    printf("\"blocks_produced\":%u,\"blocks_worked\":%u,\"blocks_reaped\":%u,\"blocks_oracle_checked\":%"PRIu64",\"complex_outputs_checked\":%"PRIu64",\"frames_submitted\":%u,\"frames_reaped\":%u,\"wire_completed\":%"PRIu64",\"dma_count\":%u,\"queue_count\":%u,\"max_dma_count\":%u,\"max_owned_banks\":%u,",runtime.block_next,pipeline.consume_next,runtime.block_reap,checked_blocks,checked_blocks*HBPIPE_OUTPUT,runtime.submit_next,runtime.complete_next,wire_completions,runtime.dma_count,qcount,max_dma_count,max_owned_banks);
    printf("\"frame_states\":[%u,%u,%u,%u],\"pipeline_states\":[%u,%u],\"copied_words\":%"PRIu64",\"copy_segments\":%"PRIu64",\"copy_wraps\":%"PRIu64",\"raw_words_checked\":%"PRIu64",\"retained_carry_words_checked\":%u,",states[0],states[1],states[2],states[3],hbpipe_status(&pipeline,0),hbpipe_status(&pipeline,1),copied_words,copy_segments,copy_wraps,raw_words_checked,adapter.fill);
    printf("\"polls\":%"PRIu64",\"worker_calls\":%"PRIu64",\"max_poll_gap\":%"PRIu64",\"max_sampled_core0_step\":%"PRIu64",\"max_worker_step\":%"PRIu64",\"max_owner_phase\":%"PRIu64",\"max_source_hold\":%"PRIu64",",poll_calls,worker_calls,max_poll_gap,max_step_cycles,max_worker_cycles,max_phase_cycles,max_source_hold);
    printf("\"native_stop_state\":{\"written\":%u,\"prepared\":%s,\"preparing\":%s,\"prepare_done\":%u,\"prepare_budget_left\":%u,\"age_cycles\":%"PRIu64",\"next_bank_owned\":%s},",(rf_index-capture.expected)&(WORDS-1),capture.prepared?"true":"false",capture.preparing?"true":"false",capture.prepare_done,runtime.prepare_words,capture.now-capture.switch_earliest,adapter.banks[(capture.active+1)%3].owned?"true":"false");
    printf("\"admission_failure\":{\"sampled_cycles\":%"PRIu64",\"failure_cycles\":%"PRIu64",\"bank\":%u,\"deadline\":%"PRIu64",\"remaining\":%"PRIu64",\"next_path_code\":%u,\"pipeline_states\":[%u,%u],\"carry_words\":%u,\"pending_raw_words\":%"PRIu64",\"counterfactual_base_step_cycles\":%"PRIu64",\"counterfactual_copied_words\":%"PRIu64",\"counterfactual_consumed_words\":%"PRIu64",\"counterfactual_copy_chunks\":%u,\"counterfactual_would_produce\":%s,\"counterfactual_failed_bank_release_base_cycles\":",admission_sampled,failure_time,admission_bank,failure_deadline,admission_remaining,failure_path,failure_pipeline_status[0],failure_pipeline_status[1],failure_fill,failure_pending_raw,failure_step_base,failure_copy_words,failure_consumed_words,failure_copy_chunks,failure_would_produce?"true":"false");
    if(failure_release_base==UINT64_MAX)printf("null},");else printf("%"PRIu64"},",failure_release_base);
    printf("\"first_accept\":{\"cycles\":%"PRIu64",\"blocks\":%"PRIu64",\"charged_cycles\":[%"PRIu64",%"PRIu64"]},\"last_accept\":{\"cycles\":%"PRIu64",\"blocks\":%"PRIu64",\"charged_cycles\":[%"PRIu64",%"PRIu64"]},",first_accept_cycle,first_accept_blocks,first_accept_charge[0],first_accept_charge[1],last_accept_cycle,last_accept_blocks,last_accept_charge[0],last_accept_charge[1]);
    printf("\"stop_charged_cycles\":[%"PRIu64",%"PRIu64"],\"stop_stall_cycles\":[%"PRIu64",%"PRIu64"],\"accounted_until_cycles\":[%"PRIu64",%"PRIu64"],\"charged_cycles\":[%"PRIu64",%"PRIu64"],\"stall_cycles\":[%"PRIu64",%"PRIu64"],\"post_stop_idle_cycles\":[%"PRIu64",%"PRIu64"],\"phase_calls\":[",stop_charge[0],stop_charge[1],stop_stall[0],stop_stall[1],ready[0],ready[1],total_charge(0),total_charge(1),stalls[0],stalls[1],idle_cycles[0],idle_cycles[1]);
    for(unsigned p=0;p<9;p++)printf("%s%"PRIu64,p?",":"",phase_calls[p]);
    printf("],\"bank_observations\":[");
    for(unsigned n=0;n<bank_observation_count;n++) {
        bank_observation *v=&bank_observations[n];
        printf("%s{\"number\":%u,\"bank\":%u,\"cycles\":%"PRIu64",\"accepted_words\":%"PRIu64",\"consumed_words\":%"PRIu64",\"blocks_produced\":%u,\"blocks_reaped\":%u,\"owned_banks\":%u,\"charged_cycles\":[%"PRIu64",%"PRIu64"]}",n?",":"",n+1,v->bank,v->cycles,v->accepted,v->consumed,v->block_next,v->block_reap,v->owned,v->charged[0],v->charged[1]);
    }
    printf("],\"cost_ledger\":[");
    for(unsigned c=0;c<2;c++){printf("%s[",c?",":"");for(unsigned k=0;k<MODEL_CATEGORIES;k++)printf("%s[%"PRIu64",%"PRIu64"]",k?",":"",events[c][k],ledger[c][k]);printf("]");}
    puts("]}");
}
int main(int argc,char **argv) {
    if(argc==2&&!strcmp(argv[1],"--selftest"))return selftest();
    if(argc!=9)return 2;
    requested_banks=(unsigned)strtoul(argv[1],NULL,10);stall_percent=(unsigned)strtoul(argv[2],NULL,10);
    phy_cycles=(unsigned)strtoul(argv[3],NULL,10);bound=(unsigned)strtoul(argv[4],NULL,10);
    inject=(unsigned)strtoul(argv[5],NULL,10);destroy_source=(unsigned)strtoul(argv[6],NULL,10);
    clock_error=(unsigned)strtoul(argv[7],NULL,10);next_phy=strtoull(argv[8],NULL,10);
    uint64_t first_phy_cycle=next_phy;
    initialize();s3_native_io io={rd,wr,NULL,bank_pointer,NULL};
    if(!s3_native_start_sink_clocked(&capture,hbnative_sink(&adapter),io,16,model_clock,NULL,clock_error))return 3;
    for(unsigned c=0;c<2;c++) {
        getcontext(&contexts[c]);contexts[c].uc_stack.ss_sp=stacks[c];contexts[c].uc_stack.ss_size=sizeof(stacks[c]);
        contexts[c].uc_link=&scheduler;makecontext(&contexts[c],c?task1:task0,0);
    }
    started=1;
    while(!stopped[0]||!stopped[1]) {
        unsigned c=stopped[0]?1:stopped[1]?0:ready[0]<=ready[1]?0:1;
        uint64_t target=ready[c],event=next_tick;
        if(phy_cycles&&next_phy<event)event=next_phy;
        if(spi_event<event)event=spi_event;if(wire_done<event)event=wire_done;if(irq_end<event)event=irq_end;
        if(event<=target) {
            advance(event);
            if(event==next_tick){for(unsigned k=0;k<2;k++)interrupt_charge(k,M_TICK,k?COST_TICK1:COST_TICK0);next_tick+=2400000;}
            if(phy_cycles&&event==next_phy) {
                if(!stopped[1]){interrupt_charge(1,M_PHY,phy_cycles);phy_busy_until=(phy_busy_until>now?phy_busy_until:now)+phy_cycles;}
                next_phy+=240000000;
            }
            if(event==spi_event||event==wire_done||event==irq_end)spi_interrupt();
        } else {advance(target);core=c;swapcontext(&scheduler,&contexts[c]);}
        if(now>UINT64_C(2400000000)){broken(110);snapshot_stop();break;}
    }
    validate_dma();validate_guards();
    for(unsigned n=0;n<adapter.fill;n++)if(adapter.carry[n]!=sample_word(adapter.produced_samples+n))broken(111);
    report(first_phy_cycle);return 0;
}

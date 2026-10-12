#include "s3_mode_switch.h"
#include <assert.h>
#include <stdio.h>
typedef struct {unsigned stops,pulses,tunes,enables;int drained,id_ready,epoch_ready,lock_ready;enum s3_mode image;uint16_t epoch;} io_state;
static bool stop(void*p){++((io_state*)p)->stops;return true;}
static int drain(void*p){return ((io_state*)p)->drained;}
static bool pulse(void*p){++((io_state*)p)->pulses;return true;}
static int identity(void*p,enum s3_mode*m){io_state*s=p;*m=s->image;return s->id_ready;}
static int epoch(void*p,uint16_t e){io_state*s=p;s->epoch=e;return s->epoch_ready;}
static bool tune(void*p,enum s3_mode m){io_state*s=p;(void)m;++s->tunes;return true;}
static int locked(void*p){return ((io_state*)p)->lock_ready;}
static bool enable(void*p){++((io_state*)p)->enables;return true;}
int main(void)
{
 io_state io={0};s3_mode_switch sw;
 s3_switch_io ops={stop,drain,pulse,identity,epoch,tune,locked,enable,&io};
 assert(s3_mode_switch_init(&sw,ops,S3_MODE_S,17));
 assert(s3_mode_switch_request(&sw,S3_MODE_T,0));assert(io.stops==1&&!io.pulses);
 assert(s3_mode_switch_step(&sw,1)&&!io.pulses); /* no reconfig before DMA/worker join */
 io.drained=1;assert(s3_mode_switch_step(&sw,2)&&io.pulses==1);
 io.id_ready=1;io.image=S3_MODE_RECOVERY;assert(s3_mode_switch_step(&sw,3)&&io.pulses==2&&!io.enables);
 io.image=S3_MODE_T;assert(s3_mode_switch_step(&sw,4)&&sw.state==S3_SWITCH_EPOCH);
 assert(s3_mode_switch_step(&sw,5)&&io.epoch==18&&!io.tunes);
 io.epoch_ready=1;assert(s3_mode_switch_step(&sw,6)&&io.tunes==1&&!io.enables);
 assert(s3_mode_switch_step(&sw,7)&&!io.enables);
 io.lock_ready=1;assert(s3_mode_switch_step(&sw,8)&&sw.state==S3_SWITCH_RUNNING&&io.enables==1);
 assert(s3_mode_switch_request(&sw,S3_MODE_S,9));
 io.image=S3_MODE_T;assert(s3_mode_switch_step(&sw,10));assert(!s3_mode_switch_step(&sw,11));assert(sw.state==S3_SWITCH_FAULT&&io.enables==1);
 assert(!s3_mode_switch_step(&sw,12));
 assert(s3_mode_switch_init(&sw,ops,S3_MODE_T,65535));assert(!s3_mode_switch_request(&sw,S3_MODE_S,13));
 assert(s3_mode_switch_init(&sw,ops,S3_MODE_T,1));assert(s3_mode_switch_request(&sw,S3_MODE_S,0));assert(!s3_mode_switch_step(&sw,100000));
 puts("PASS C control: no pulse before drain, two NOR hops, identity/epoch/lock acknowledgements, fail-stop and timeout");
}

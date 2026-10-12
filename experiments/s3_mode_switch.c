#include "s3_mode_switch.h"
static enum s3_mode next(enum s3_mode m){return m==S3_MODE_T?S3_MODE_S:m==S3_MODE_S?S3_MODE_RECOVERY:S3_MODE_T;}
static bool fail(s3_mode_switch *s){s->state=S3_SWITCH_FAULT;s->io.stop(s->io.ctx);return false;}
bool s3_mode_switch_init(s3_mode_switch *s,s3_switch_io io,enum s3_mode mode,uint16_t epoch)
{
 if(!s||mode<S3_MODE_T||mode>S3_MODE_S||!epoch||!io.stop||!io.drain||!io.pulse||!io.identity||!io.epoch||!io.tune||!io.locked||!io.enable)return false;
 *s=(s3_mode_switch){.io=io,.current=mode,.target=mode,.epoch=epoch,.state=S3_SWITCH_RUNNING};return true;
}
bool s3_mode_switch_request(s3_mode_switch *s,enum s3_mode target,uint64_t now)
{
 if(!s||s->state!=S3_SWITCH_RUNNING||target<S3_MODE_T||target>S3_MODE_S)return false;
 if(target==s->current)return true;
 if(s->epoch==65535||now>UINT64_MAX-5000000)return fail(s);
 if(!s->io.stop(s->io.ctx))return fail(s);
 s->target=target;s->state=S3_SWITCH_DRAIN;s->deadline=now+100000;s->hops=0;return true;
}
bool s3_mode_switch_step(s3_mode_switch *s,uint64_t now)
{
 if(!s||s->state==S3_SWITCH_FAULT)return false;
 if(s->state==S3_SWITCH_RUNNING)return true;
 if(now>=s->deadline||now>UINT64_MAX-5000000)return fail(s);
 int rc;
 switch(s->state) {
 case S3_SWITCH_DRAIN:
  rc=s->io.drain(s->io.ctx);if(rc<0)return fail(s);
  if(rc==1) {
   s->expected=next(s->current);++s->hops;
   if(!s->io.pulse(s->io.ctx))return fail(s);
   s->state=S3_SWITCH_BOOT;s->deadline=now+2000000;
  }break;
 case S3_SWITCH_BOOT: {
  enum s3_mode image;
  rc=s->io.identity(s->io.ctx,&image);if(rc<0)return fail(s);
  if(rc==1) {
   if(image!=s->expected||s->hops>2)return fail(s);
   s->current=image;
   if(image!=s->target) {
    s->expected=next(image);++s->hops;
    if(!s->io.pulse(s->io.ctx))return fail(s);
    s->deadline=now+2000000;
   } else {++s->epoch;s->state=S3_SWITCH_EPOCH;s->deadline=now+100000;}
  }break;
 }
 case S3_SWITCH_EPOCH:
  rc=s->io.epoch(s->io.ctx,s->epoch);if(rc<0)return fail(s);
  if(rc==1) {
   if(!s->io.tune(s->io.ctx,s->target))return fail(s);
   s->state=S3_SWITCH_LOCK;s->deadline=now+5000000;
  }break;
 case S3_SWITCH_LOCK:
  rc=s->io.locked(s->io.ctx);if(rc<0)return fail(s);
  if(rc==1) {
   s->state=S3_SWITCH_ENABLE;s->deadline=now+100000;
  }break;
 case S3_SWITCH_ENABLE:
  rc=s->io.enable(s->io.ctx);if(rc<0)return fail(s);
  if(rc==1)s->state=S3_SWITCH_RUNNING;
  break;
 default:return fail(s);
 }
 return true;
}

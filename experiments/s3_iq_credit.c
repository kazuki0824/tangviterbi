#include "s3_iq_credit.h"
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#define HOT IRAM_ATTR
#else
#define HOT
#endif
bool s3_iq_credit_init(s3_iq_credit *s,unsigned epoch,unsigned (*gray)(void *),void *ctx)
{
 if(!s||!epoch||epoch>65535||!gray||gray(ctx)!=0||gray(ctx)!=0)return false;
 memset(s,0,sizeof(*s));s->epoch=epoch;s->gray=gray;s->context=ctx;return true;
}
int HOT s3_iq_credit_take(void *ctx,unsigned epoch,uint32_t offset)
{
 s3_iq_credit *s=ctx;
 if(!s||s->fault)return -1;
 if(epoch!=s->epoch||offset!=s->offset){s->fault=true;return -1;}
 unsigned a=s->gray(s->context),b=s->gray(s->context);
 if(a>3||b>3){s->fault=true;return -1;}
 if(a!=b)return 0;
 unsigned value=b^(b>>1),delta=(value-s->last)&3;
 if(s->available+delta>2){s->fault=true;return -1;}
 s->last=value;s->available+=delta;
 if(!s->available)return 0;
 --s->available;s->offset+=4096;return 1;
}

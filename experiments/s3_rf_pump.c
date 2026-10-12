#include "s3_rf_pump.h"
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#define HOT IRAM_ATTR
#else
#define HOT
#endif
static bool HOT fail(s3_rf_pump *s)
{s->fault=true;s3_native_stop(s->capture);return false;}
bool s3_rf_pump_init(s3_rf_pump *s,s3_tx_ring *ring,s3_native_capture *capture,
                     s3_spi_port *a,s3_spi_port *b,unsigned (*gray)(void *),void *ctx)
{
 if(!s||!ring||!capture||!a||!b||!gray||!ring->epoch||ring->submit_sequence||
    ring->retire_sequence||capture->running||a->busy||b->busy||a->poisoned||b->poisoned)return false;
 unsigned g0=gray(ctx),g1=gray(ctx);
 if(g0!=0||g1!=0)return false; /* do not adopt a stale FPGA epoch */
 memset(s,0,sizeof(*s));s->ring=ring;s->capture=capture;s->ports[0]=a;s->ports[1]=b;
 s->gray=gray;s->gray_context=ctx;s->quad_RF_allowed=true;s->credit_limit=4;return true;
}
bool HOT s3_rf_pump_step(void *context)
{
 s3_rf_pump *s=context;
 if(!s||s->fault)return false;
 if(!s->credit_limit||s->credit_limit>4||s->submitted-s->retired>s->credit_limit)return fail(s);
 /* IRQ callbacks do not recycle these leases; the single owner does. */
 for(unsigned p=0;p<2;++p)if(s->transfers[p].count) {
  esp_err_t rc=s3_rf_reap(&s->transfers[p]);
  if(rc!=ESP_OK&&rc!=ESP_ERR_TIMEOUT)return fail(s);
 }
 unsigned a=s->gray(s->gray_context),b=s->gray(s->gray_context);
 if(a>7||b>7)return fail(s);
 if(a!=b)return true; /* bounded retry at the next RF service, no busy wait */
 unsigned value=b^(b>>1)^(b>>2),delta=(value-s->last_binary)&7;
 if(delta>s->submitted-s->retired)return fail(s);
 s->retired+=delta;s->last_binary=value;
 for(unsigned p=0;p<2;++p) {
  if(p==1&&!s->quad_RF_allowed)continue;
  if(s->ports[p]->poisoned)return fail(s);
  if(s->ports[p]->busy)continue; /* FFT/RPC may own a shared port */
  unsigned credit=s->credit_limit-(s->submitted-s->retired);
  unsigned n=s3_ring_ready_pages(s->ring),limit=p==0?s->credit_limit:1;
  if(n>credit)n=credit;
  if(n>limit)n=limit;
  if(!n)continue;
  esp_err_t rc=s3_rf_submit(&s->transfers[p],s->ports[p],s->ring,n);
  if(rc!=ESP_OK)return fail(s);
  s->submitted+=n;
 }
 return true;
}

#include "s3_parallel_pack.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static _Alignas(16) uint8_t data[4][S3_PP_CHUNK];
static uint32_t words[S3_PP_WORDS];
static s3_parallel_pack pack;
static const uint64_t epoch=UINT64_C(90000000000);
typedef struct {uint64_t start,finish;unsigned reads;} test_clock;
static uint64_t clock_read(void *ctx) {
 test_clock*c=ctx;return c->reads++?c->finish:c->start;
}
static void init(void) {
 uint8_t *buffers[4]={data[0],data[1],data[2],data[3]};
 memset(data,0xcc,sizeof(data));
 for(unsigned i=0;i<S3_PP_WORDS;++i)words[i]=(i*17413u)&0xfffff;
 assert(s3_pp_init(&pack,buffers)==S3_PP_OK);
 // Both workers receive 4 pairs: even the final slice needs a post-clock check.
 assert(s3_pp_accept(&pack,0,words,0,16,0,epoch,epoch+100)==S3_PP_OK);
}
static void failure(uint64_t finish,unsigned max_pairs) {
 init();unsigned done=0;
 test_clock a={epoch+10,epoch+20,0};
 assert(s3_pp_step_clocked(&pack,0,4,clock_read,&a,30,&done)==S3_PP_OK);
 test_clock b={epoch+30,finish,0};
 assert(s3_pp_step_clocked(&pack,1,max_pairs,clock_read,&b,50,&done)==S3_PP_DEADLINE);
 assert(done==max_pairs && b.reads==2);
 assert(s3_pp_collect(&pack,epoch+200)==S3_PP_FAULT);
 assert(pack.banks[0].owned && pack.count==1 && pack.published==0);
 assert(s3_pp_reclaim(&pack,0)==S3_PP_FAULT);
 const uint8_t*out;uint64_t seq;
 assert(s3_pp_take(&pack,&seq,&out)==S3_PP_FAULT);
 assert(s3_pp_step_clocked(&pack,1,4,clock_read,&b,50,&done)==S3_PP_FAULT);
}
int main(void) {
 failure(epoch+100,4); // completion exactly at the exclusive deadline
 failure(epoch+101,4); // last worker cannot publish a late final slice
 failure(epoch+81,4);  // measured bound exceeded, even before bank deadline
 failure(epoch+29,4);  // clock regressed / wrong epoch
 failure(epoch+101,1); // partial slice fault also retains ownership
 init();unsigned done;
 test_clock a={epoch+1,epoch+51,0},b={epoch+40,epoch+90,0};
 assert(s3_pp_step_clocked(&pack,0,4,clock_read,&a,50,&done)==S3_PP_OK);
 assert(s3_pp_step_clocked(&pack,1,4,clock_read,&b,50,&done)==S3_PP_OK);
 // Late collection is allowed if both workers actually finished on time.
 assert(s3_pp_collect(&pack,epoch+200)==S3_PP_OK);
 assert(!pack.banks[0].owned && pack.published==40);
 init();test_clock c={epoch+50,epoch+51,0};
 assert(s3_pp_step_clocked(&pack,0,4,clock_read,&c,50,&done)==S3_PP_DEADLINE);
 assert(done==0 && c.reads==1);
 for(unsigned i=0;i<sizeof(data);++i)assert(((uint8_t*)data)[i]==0xcc);
 init();assert(s3_pp_step_clocked(&pack,0,4,NULL,NULL,50,&done)==S3_PP_INVALID);
 assert(done==0 && atomic_load(&pack.fault));
 puts("PASS final/partial late completion, bound overrun, clock regression, late collect, precheck, null clock");
}

#include "s3_fft_worker.h"
#include "s3_fft_simd_tiles.h"
#include <stdlib.h>
typedef struct {
    s3_fft_worker worker;
    unsigned polls[2];
    int fail_core,tile_failure;
    unsigned fail_poll;
    atomic_uint calls;
} fixture;
static bool service(void *ctx,unsigned core)
{
    fixture *f=ctx;
    ++f->polls[core];
    return (int)core!=f->fail_core||f->polls[core]!=f->fail_poll;
}
static int tile(void *ctx,int16_t *d,const int16_t *t,unsigned s,unsigned b,unsigned n)
{
    fixture *f=ctx;
    atomic_fetch_add_explicit(&f->calls,1,memory_order_relaxed);
    return f->tile_failure?-1:s3_fft_simd_tile(d,t,s,b,n);
}
fixture *worker_create(int16_t *d,const int16_t *t,int core,unsigned poll,int tile_fail)
{
    fixture *f=calloc(1,sizeof(*f));
    if(!f)return NULL;
    f->fail_core=core;f->fail_poll=poll;f->tile_failure=tile_fail;
    atomic_init(&f->calls,0);
    if(!s3_fft_worker_init(&f->worker,d,t,service,f,tile,f)){free(f);return NULL;}
    return f;
}
void worker_destroy(fixture *f){free(f);}
int worker_step(fixture *f,unsigned c){return s3_fft_worker_step(&f->worker,c);}
bool worker_ready(fixture *f){return s3_fft_worker_ready(&f->worker);}
unsigned worker_progress(fixture *f,unsigned c){return atomic_load(&f->worker.progress[c]);}
unsigned worker_calls(fixture *f){return atomic_load(&f->calls);}
unsigned worker_polls(fixture *f,unsigned c){return f->polls[c];}

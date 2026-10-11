#ifndef S3_FFT_WORKER_H
#define S3_FFT_WORKER_H
#include <stdbool.h>
#include <stdint.h>
#include <stdatomic.h>

/* One exclusively owned 8192-point frame. Initialize before either worker;
 * stop/join BOTH workers before reset, freeing buffers, or changing callbacks.
 * One caller per core. Each step services RF/transport before and after at
 * most 64 butterflies. A stage barrier RETURNS to the caller; it never spins
 * with interrupts masked. Core0 alone owns native RF/packing; core1's service
 * callback must not modify that RF object. RTOS task creation/pinning, frame
 * ingress/egress ownership and measured callback/tile WCET remain caller gates.
 * All callbacks/buffers used on S3 must be internal/IRAM as appropriate. High
 * priority/NMI code cannot use PIE. No allocation or output reorder occurs.
 * Output is all 8192 Q15 bins in reverse13 index order, scaled by 1/8192.
 */
typedef bool (*s3_fft_service_fn)(void *,unsigned core);
typedef int (*s3_fft_tile_fn)(void *,int16_t *,const int16_t *,
                            unsigned stage,unsigned begin,unsigned count);
typedef struct {
    atomic_uint progress[2], fault;
    int16_t *data;
    const int16_t *table;
    s3_fft_service_fn service;
    s3_fft_tile_fn tile;
    void *service_context,*tile_context;
} s3_fft_worker;
enum { S3_FFT_WORKER_ERROR=-1, S3_FFT_WORKER_WAIT=0,
       S3_FFT_WORKER_PROGRESS=1, S3_FFT_WORKER_DONE=2 };
bool s3_fft_worker_init(s3_fft_worker *,int16_t *,const int16_t *,
                        s3_fft_service_fn,void *,s3_fft_tile_fn,void *);
int s3_fft_worker_step(s3_fft_worker *,unsigned core);
bool s3_fft_worker_ready(const s3_fft_worker *);
/* Null tile callback selects the real SIMD tile implementation. A test backend
 * may supply a callback, but its timing/numerical results do not qualify SIMD.
 */
#endif

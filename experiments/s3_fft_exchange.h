#ifndef S3_FFT_EXCHANGE_H
#define S3_FFT_EXCHANGE_H
#include "s3_spi_transport.h"
#include "s3_fft_tasks.h"
#ifdef ESP_PLATFORM
enum s3_frame_state {S3_FRAME_FREE,S3_FRAME_READING,S3_FRAME_READY,S3_FRAME_COMPUTING,S3_FRAME_REORDERING,S3_FRAME_WRITING};
typedef struct {int16_t *data;uint32_t sequence,offset;unsigned pages_read,reordered;enum s3_frame_state state;} s3_frame_slot;
/* A single core0 owner. Two full frames, no scratch copies or omitted bins.
 * ready reads ACTUAL FPGA status for epoch/offset (not a local timer). Returns
 * -1 fault, 0 not yet published, 1 immutable complete page. A successful DMA
 * read acknowledges that page to the FPGA. No callback may change these
 * objects or call SPI on the same ports. Each frame is retained through its
 * entire return DMA; output contains ALL Q15 bins in natural frequency order.
 * Bit reversal runs in bounded 64-point slices between RF service calls.
 * SDK errors retain both the frame and port for fail-stop.
 * Status/FPGA DSP and external IO timing are separate integration obligations.
 */
typedef struct {
 s3_spi_port *input,*output;s3_fft_tasks *tasks;s3_frame_slot slots[2];
 const int16_t *table;s3_fft_service_fn service;void *service_context;
 int (*ready)(void *,unsigned,uint32_t);void *ready_context;
 unsigned points,epoch;uint32_t next_read,next_compute,next_write,completed;
 int rx_slot,tx_slot,compute_slot;bool fault;
} s3_fft_exchange;
bool s3_fft_exchange_open(s3_fft_exchange *,s3_spi_port *,s3_spi_port *,s3_fft_tasks *,
 int16_t *,int16_t *,const int16_t *,unsigned points,unsigned epoch,
 s3_fft_service_fn,void *,int (*ready)(void *,unsigned,uint32_t),void *);
bool s3_fft_exchange_step(s3_fft_exchange *);
/* Used AFTER RF stop and task join: only reaps DMA, never submits anything.
 * Pending/error preserves all leases. The owner must not overwrite any frame
 * or mode union until this returns true. */
bool s3_fft_exchange_drained(s3_fft_exchange *);
#endif
#endif

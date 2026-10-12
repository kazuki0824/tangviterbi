#ifndef S3_PIPELINE_ESP_H
#define S3_PIPELINE_ESP_H
#include "s3_fft_tasks.h"
#include "s3_fft_capture_service.h"
#include "s3_rf_pump.h"
#include "s3_fft_exchange.h"
#ifdef ESP_PLATFORM
typedef struct {
 s3_spi_port ports[2];
 spi_multi_transaction_t octal[8],quad[1];
 s3_tx_ring ring;
 s3_capture_bridge bridge;
 s3_native_capture capture;
 s3_rf_pump pump;
 s3_fft_capture_service service;
 s3_fft_tasks tasks;
 s3_fft_exchange exchange;
 bool opened,FFT_enabled;
} s3_pipeline_esp;
/* RF is stopped on entry. board_epoch_verified means image identity, stream
 * epoch and the receiver's zero credit cursor have actually been acknowledged.
 * It is not supplied by this adapter. PHY/RF dump validation is also separate.
 * Main task is pinned to core0; stack/ring/table/frame arenas are internal.
 * Zero-initialize before the first open; never copy an opened pipeline.
 */
bool s3_pipeline_esp_open(s3_pipeline_esp *,void *ring,StackType_t *peer_stack,
                          unsigned peer_stack_bytes,unsigned epoch,bool board_epoch_verified);
bool s3_pipeline_esp_start_RF(s3_pipeline_esp *,unsigned rate_msps,
                              unsigned pack_words,uint32_t pack_slice_cycles);
bool s3_pipeline_esp_step(s3_pipeline_esp *);
bool s3_pipeline_esp_begin_FFT(s3_pipeline_esp *,int16_t *,const int16_t *,unsigned points);
/* Use instead of manual begin_FFT for the complete DMA/frame lifetime.
 * Call after start_RF(T). Status must certify the FPGA IQ page epoch/offset.
 * Stop the pipeline before changing points or the two frame arenas. */
bool s3_pipeline_esp_enable_FFT(s3_pipeline_esp *,int16_t *,int16_t *,const int16_t *,unsigned,
                                int (*ready)(void *,unsigned,uint32_t),void *);
bool s3_pipeline_esp_close(s3_pipeline_esp *,TickType_t timeout);
#endif
#endif

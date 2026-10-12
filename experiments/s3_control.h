#ifndef S3_CONTROL_H
#define S3_CONTROL_H
#include "s3_spi_transport.h"
enum {S3_CONTROL_BYTES=32};
typedef struct {unsigned image,epoch;uint32_t IQ_offset,flags,build_tag,nonce;} s3_control_status;
typedef struct {
 s3_spi_port *port;_Alignas(16) uint8_t payload[S3_CONTROL_BYTES];
 uint32_t nonce;unsigned pending;bool fault,valid;s3_control_status status;
} s3_control;
/* Same owner as RF/FFT on SPI3. No copy/reset until DMA returns.
 * Successful request DMA is NOT an epoch/enable ACK: query the real CSR.
 * Reset only after all previous stream owners joined. */
bool s3_control_init(s3_control *,s3_spi_port *);
esp_err_t s3_control_query(s3_control *);
esp_err_t s3_control_epoch(s3_control *,unsigned epoch);
esp_err_t s3_control_enable(s3_control *,unsigned epoch,bool enable);
/* -1 fail-stop, 0 pending/invalid startup reply, 1 complete.
 * Commands return request completion, not applied-CSR acknowledgement. */
int s3_control_poll(s3_control *);
bool s3_control_decode(const uint8_t *,uint32_t nonce,s3_control_status *);
#endif

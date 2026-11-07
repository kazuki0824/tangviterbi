#ifndef S3_PARALLEL_SPI_H
#define S3_PARALLEL_SPI_H
#include "s3_parallel_pack.h"
#include "s3_spi_transport.h"
typedef struct {
 s3_parallel_pack *pack;
 s3_spi_port *port;
 uint64_t sequence;
 bool active;
} s3_pp_transfer;
/* Zero initialize transfer. One coordinator owns BOTH ports' submit/reap and
 * pack accept/collect. Workers own only their packing jobs. Queue/prepare
 * failures latch a fault and retain the lease; stopping hardware/quiescence
 * is required before init. No automatic retry or payload discard.
 */
esp_err_t s3_pp_spi_submit(s3_pp_transfer*,s3_parallel_pack*,s3_spi_port*,unsigned epoch);
esp_err_t s3_pp_spi_reap(s3_pp_transfer*);
#endif

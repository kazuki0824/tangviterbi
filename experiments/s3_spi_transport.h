#ifndef S3_SPI_TRANSPORT_H
#define S3_SPI_TRANSPORT_H
#include "s3_transport.h"
#include "driver/spi_master.h"
#include "esp_private/spi_master_internal.h"

/* ESP-IDF v5.5.1 only. The SCT interface is private, explicitly version-pinned.
 * One scheduler owns each port. No simultaneous normal/SCT or polling use.
 * Max one batch in flight. Caller retains every payload and descriptor until
 * reap returns ESP_OK; on an unexpected SDK error the port stays poisoned.
 * Pin/electrical timing, FPGA ready/status and RF acquisition are not provided.
 */
enum { S3_SPI_MAX_SEGMENTS = 8 };
typedef struct {
    spi_device_handle_t device;
    spi_host_device_t host;
    unsigned lanes, count, capacity;
    bool sct, busy, poisoned;
    spi_multi_transaction_t *segments;
} s3_spi_port;

/* Caller supplies board-specific pins. This overwrites max_transfer_sz/flags;
 * DMA pool is sized for configuration + two payload descriptors per segment.
 */
esp_err_t s3_spi_open(s3_spi_port *port, spi_host_device_t host,
                       const spi_bus_config_t *pins, int cs, unsigned lanes,
                       bool sct, spi_multi_transaction_t *storage, unsigned capacity);
esp_err_t s3_spi_prepare_pages(s3_spi_port *port, unsigned stream, unsigned epoch,
                                uint32_t offset, void *const payloads[], unsigned pages);
esp_err_t s3_spi_prepare(s3_spi_port *port, unsigned stream, unsigned epoch,
                          uint32_t offset, void *payload, unsigned pages);
esp_err_t s3_spi_queue(s3_spi_port *port);
esp_err_t s3_spi_reap(s3_spi_port *port);
esp_err_t s3_spi_close(s3_spi_port *port);
#endif

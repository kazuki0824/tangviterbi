#ifndef S3_RF_PUMP_H
#define S3_RF_PUMP_H
#include "s3_spi_transport.h"
#include "s3_native_capture.h"
/* Two Gray-code GPIO bits carry RF consumer retirement modulo four.
 * Exactly one host scheduler owns both SPI ports and the ring. Cap total
 * queued-but-not-consumed pages at THREE, so every modulo-four delta is
 * unambiguous, including zero. DMA completion alone is NOT remote credit.
 * Epoch is set only while RF/SPI/FPGA are stopped; initial retire is zero.
 * One callback reads the complete two-bit Gray value, twice for stability.
 * This is a concrete interface proposal, not verified board IO timing.
 */
typedef struct {
 s3_tx_ring *ring;
 s3_native_capture *capture;
 s3_spi_port *ports[2];
 s3_rf_transfer transfers[2];
 unsigned (*gray)(void *);
 void *gray_context;
 uint32_t submitted,retired;
 unsigned last_binary;
 bool fault,quad_RF_allowed;
} s3_rf_pump;
bool s3_rf_pump_init(s3_rf_pump *,s3_tx_ring *,s3_native_capture *,
                     s3_spi_port *,s3_spi_port *,unsigned (*)(void *),void *);
bool s3_rf_pump_step(void *);
#endif

#ifndef S3_PAGE_CREDIT_H
#define S3_PAGE_CREDIT_H
#include "s3_transport.h"
/* One scheduler coordinates BOTH RF ports. DMA completion frees the host
 * buffer but never FPGA credit. Only a validated retired frontier frees the
 * receiver's advertised slots. Mode reset requires stopped and drained IO. */
typedef struct {
    uint32_t next, retired;
    uint16_t epoch;
    uint8_t window;
    bool synced, poisoned;
} s3_page_credit;
int s3_credit_init_window(s3_page_credit *credit, unsigned epoch, uint32_t first_sequence, unsigned window);
int s3_credit_init(s3_page_credit *credit, unsigned epoch, uint32_t first_sequence);
int s3_credit_status(s3_page_credit *credit, const uint8_t response[16]);
int s3_credit_reserve(s3_page_credit *credit, unsigned pages, uint32_t *first_sequence);
void s3_credit_poison(s3_page_credit *credit);
#endif

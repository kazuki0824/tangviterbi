#ifndef S3_IQ_CREDIT_H
#define S3_IQ_CREDIT_H
#include <stdbool.h>
#include <stdint.h>
/* Two immutable FPGA IQ pages limit unseen publications to two. One main
 * owner consumes this credit exactly once before starting each IQ read DMA.
 * Epoch/image/zero GPIO counters must be acknowledged before RF enable.
 * No wire data is decimated/requantized. GPIO synchronizer/IO timing is a
 * separate board requirement; repeated software reads are not IO STA. */
typedef struct {
 unsigned (*gray)(void *);void *context;unsigned epoch,last,available;
 uint32_t offset;bool fault;
} s3_iq_credit;
bool s3_iq_credit_init(s3_iq_credit *,unsigned,unsigned (*)(void *),void *);
int s3_iq_credit_take(void *,unsigned,uint32_t);
#endif

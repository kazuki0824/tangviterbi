/* Experimental replacement translation unit for s3_parallel_pack.c.
 * Compile this OR the baseline, never both. Preserve all ownership/clock logic;
 * only substitute the eight-word packing primitive for target comparison. */
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#define HOT IRAM_ATTR
#else
#define HOT
#endif
#define S3_HOT HOT
#include "s3_iq10_inline.h"
#define S3_IQ10_BLOCK_H
#include "s3_parallel_pack.c"

#ifndef S3_RAW_TRANSFER_CONFIG_H
#define S3_RAW_TRANSFER_CONFIG_H
/* Whole-program build option: packer, SPI driver and FPGA receiver length
 * must agree. Four physical 32-KiB arenas are retained in either mode. */
#ifndef S3_RAW_TRANSFER_BYTES
#define S3_RAW_TRANSFER_BYTES 32768
#endif
#if S3_RAW_TRANSFER_BYTES != 16384 && S3_RAW_TRANSFER_BYTES != 32768
#error "raw transfer size must be 16384 or 32768"
#endif
#endif

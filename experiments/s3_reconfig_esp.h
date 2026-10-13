#ifndef S3_RECONFIG_ESP_H
#define S3_RECONFIG_ESP_H
#include <stdbool.h>
#ifdef ESP_PLATFORM
/* GPIO40 -> external bidirectional open-drain 3.3/1.8 V translator ->
 * FPGA pin9/R18 RECONFIG_N. This is NOT a direct 3.3 V connection.
 * Boot strap and valid T/S/recovery images in BOARD EXTERNAL NOR required.
 * quiescent verifies RF stopped, all workers joined and all DMA returned.
 * Configure/init only while the system is already quiescent. */
typedef struct {bool (*quiescent)(void *);void *context;bool opened;} s3_reconfig_esp;
bool s3_reconfig_esp_open(s3_reconfig_esp *,bool (*)(void *),void *);
bool s3_reconfig_esp_pulse(void *);
#endif
#endif

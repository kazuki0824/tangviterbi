/* Link-only resource probe. This is not a receiver firmware or a timing test. */
#include <stdint.h>
#include <stdio.h>
#include "esp_attr.h"
#include "heap_memory_layout.h"

SOC_RESERVE_MEMORY_REGION(0x3fcb0000, 0x3fce0000, s3_rf_dump);

DMA_ATTR uint8_t rf_packed_queue[32768];
DMA_ATTR uint8_t link_staging[PROBE_LINKS][2][4092];
#if PROBE_TERRESTRIAL
DMA_ATTR uint8_t fft_transfer_slots[2][33792];
DRAM_ATTR int16_t fft_twiddle_reservation[16384];
#endif
volatile uintptr_t probe_keep;

void app_main(void)
{
    // Live references prevent section GC; no PSRAM fallback or fake malloc fit.
    probe_keep = (uintptr_t)rf_packed_queue ^ (uintptr_t)link_staging;
#if PROBE_TERRESTRIAL
    probe_keep ^= (uintptr_t)fft_transfer_slots ^ (uintptr_t)fft_twiddle_reservation;
#endif
    printf("Link-only probe: T=%d links=%d; RF/FFT/PHY are not running.\n",
           PROBE_TERRESTRIAL, PROBE_LINKS);
}

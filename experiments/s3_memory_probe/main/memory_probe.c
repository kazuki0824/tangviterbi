/* Link-only resource probe. This is not a receiver firmware or a timing test. */
#include <stdint.h>
#include <stdio.h>
#include "esp_attr.h"
#include "heap_memory_layout.h"

SOC_RESERVE_MEMORY_REGION(0x3fcb0000, 0x3fce0000, s3_rf_dump);

DMA_ATTR uint8_t rf_packed_queue[32768];
#if PROBE_ZEROCOPY
// Proposed scatter/gather data ownership: payload remains in RF queue or FFT
// slots until DMA completion. These are reservations, not an implemented DMA.
DMA_ATTR uint8_t link_headers[PROBE_LINKS][2][16];
DMA_ATTR uint8_t link_descriptor_reserve[PROBE_LINKS][512];
#else
DMA_ATTR uint8_t link_staging[PROBE_LINKS][2][4092];
#endif
#if PROBE_TERRESTRIAL
#if PROBE_ZEROCOPY
DMA_ATTR uint8_t fft_transfer_slots[2][32768];
// IDF v5.5.1 exposes [0x3fce0000, 0x3fce9710) as internal heap at boot.
// Reserve a 16-KiB SIMD-aligned arena from that exact interval. It is never
// placed in ELF .data/.bss or used before app_main; startup code may use it.
// The tile kernel needs N/2 complex Q15 twiddles: 8192*2 = 16384 bytes.
SOC_RESERVE_MEMORY_REGION(0x3fce0000, 0x3fce4000, s3_fft_twiddle);
static int16_t *const fft_twiddle_reservation = (int16_t *)0x3fce0000;
#else
DMA_ATTR uint8_t fft_transfer_slots[2][33792];
DRAM_ATTR int16_t fft_twiddle_reservation[16384];
#endif
#endif
volatile uintptr_t probe_keep;

void app_main(void)
{
    // Live references prevent section GC; no PSRAM fallback or fake malloc fit.
    probe_keep = (uintptr_t)rf_packed_queue;
#if PROBE_ZEROCOPY
    probe_keep ^= (uintptr_t)link_headers ^ (uintptr_t)link_descriptor_reserve;
#else
    probe_keep ^= (uintptr_t)link_staging;
#endif
#if PROBE_TERRESTRIAL
    probe_keep ^= (uintptr_t)fft_transfer_slots ^ (uintptr_t)fft_twiddle_reservation;
#if PROBE_ZEROCOPY
    // Explicit late initialization; no loader/static initializer touches it.
    for (unsigned i=0; i<8192; ++i) fft_twiddle_reservation[i] = 0;
#endif
#endif
    printf("Link-only probe: T=%d links=%d; RF/FFT/PHY are not running.\n",
           PROBE_TERRESTRIAL, PROBE_LINKS);
}

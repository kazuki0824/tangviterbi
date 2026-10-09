/* Link-only resource probe. This is not a receiver firmware or a timing test. */
#include <stdint.h>
#include <stdio.h>
#include "esp_attr.h"
#include "heap_memory_layout.h"
#if PROBE_TRANSPORT
#include "s3_spi_transport.h"
#include "s3_fft_tiles.h"
#include "hal/dma_types.h"
static s3_spi_port transport_ports[2];
static spi_multi_transaction_t octal_segments[8], quad_segments[1];
static s3_tx_ring transport_ring;
static s3_iq10_packer transport_packer;
static s3_rf_transfer transport_RF_transfers[2];
const uint32_t transport_object_sizes[] = {
    sizeof(s3_spi_port), sizeof(spi_multi_transaction_t), sizeof(s3_tx_ring),
    sizeof(dma_descriptor_align4_t), 24*2*sizeof(dma_descriptor_align4_t),
    2*2*sizeof(dma_descriptor_align4_t), 8*60, ATOMIC_INT_LOCK_FREE
};
#endif

SOC_RESERVE_MEMORY_REGION(0x3fcb0000, 0x3fce0000, s3_rf_dump);

#if PROBE_LATE_RF
// IDF enables the non-OS startup-stack heap before calling app_main. This
// entire interval is excluded from that heap; no pre-app_main accesses.
SOC_RESERVE_MEMORY_REGION(0x3fce4000, 0x3fcec000, s3_late_rf_queue);
static uint8_t *const rf_packed_queue = (uint8_t *)0x3fce4000;
#else
DMA_ATTR uint8_t rf_packed_queue[32768];
#endif
#if PROBE_TRANSPORT
// Actual transaction objects above replace the old 544 B/port proxy.
// Runtime SDK allocations (including SCT conf buffers) are NOT static BSS.
#elif PROBE_ZEROCOPY
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
#if PROBE_TRANSPORT
    probe_keep ^= (uintptr_t)transport_ports ^ (uintptr_t)octal_segments ^
        (uintptr_t)quad_segments ^ (uintptr_t)&transport_ring ^ (uintptr_t)transport_object_sizes ^
        (uintptr_t)&transport_packer ^ (uintptr_t)transport_RF_transfers;
    // Retain real SDK/adapter/kernel call graphs without claiming a hardware
    // run or choosing unverified pins in this link-only program.
    probe_keep ^= (uintptr_t)&s3_spi_open ^ (uintptr_t)&s3_spi_prepare ^
        (uintptr_t)&s3_spi_queue ^ (uintptr_t)&s3_spi_reap ^ (uintptr_t)&s3_spi_close ^
        (uintptr_t)&s3_ring_begin ^ (uintptr_t)&s3_ring_publish ^ (uintptr_t)&s3_ring_take ^
        (uintptr_t)&s3_ring_complete ^ (uintptr_t)&s3_ring_reset ^ (uintptr_t)&s3_ring_undo_take;
    probe_keep ^= (uintptr_t)&s3_iq10_init ^ (uintptr_t)&s3_iq10_push ^ (uintptr_t)&s3_iq10_discard;
    probe_keep ^= (uintptr_t)&s3_rf_submit ^ (uintptr_t)&s3_rf_reap;
    probe_keep ^= (uintptr_t)&s3_fft_reverse_tile ^ (uintptr_t)&s3_fft_stage_tile;
#elif PROBE_ZEROCOPY
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

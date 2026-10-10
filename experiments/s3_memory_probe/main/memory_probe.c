/* Link-only resource probe. This is not a receiver firmware or a timing test. */
#ifndef PROBE_QUARTER_FFT
#define PROBE_QUARTER_FFT 0
#endif
#include <stdint.h>
#include <stdio.h>
#include "esp_attr.h"
#include "heap_memory_layout.h"
#include "sdkconfig.h"
#if PROBE_RS_OFFLOAD
#include "s3_rs_workspace.h"
#if !PROBE_ROM_SAFE || !PROBE_UPPER_FFT || !PROBE_TERRESTRIAL
#error "RS mode union requires the ROM-safe two-slot terrestrial memory plan"
#endif
#endif
#if PROBE_TRANSPORT
#include "s3_spi_transport.h"
#include "s3_fft_tiles.h"
#include "s3_capture_bridge.h"
#include "s3_native_capture.h"
#include "hal/dma_types.h"
static s3_spi_port transport_ports[2];
static spi_multi_transaction_t octal_segments[8], quad_segments[1];
static s3_tx_ring transport_ring;
static s3_page_credit transport_credit;
DMA_ATTR __attribute__((aligned(32))) uint8_t credit_status_response[16];
const uint32_t credit_object_sizes[]={sizeof(s3_page_credit),sizeof(credit_status_response)};
static s3_iq10_packer transport_packer;
static s3_rf_transfer transport_RF_transfers[2];
static s3_capture_bridge capture_bridge;
static s3_native_capture native_capture;
const uint32_t transport_object_sizes[] = {
    sizeof(s3_spi_port), sizeof(spi_multi_transaction_t), sizeof(s3_tx_ring),
    sizeof(dma_descriptor_align4_t), 24*2*sizeof(dma_descriptor_align4_t),
    2*2*sizeof(dma_descriptor_align4_t), 8*60, ATOMIC_INT_LOCK_FREE,
    sizeof(s3_capture_bridge)
};
#endif

SOC_RESERVE_MEMORY_REGION(0x3fcb0000, 0x3fce0000, s3_rf_dump);

#if PROBE_LATE_RF
// IDF enables the non-OS startup-stack heap before calling app_main. This
// entire interval is excluded from that heap; no pre-app_main accesses.
#if PROBE_RING64
#if !CONFIG_ESP32S3_DATA_CACHE_32KB
#error "64 KiB RF queue requires the audited 32 KiB data cache layout"
#endif
#if PROBE_ROM_SAFE
// Rev0 ROM reserves [0x3fceee34,0x3fcf0000); never reclaim it.
SOC_RESERVE_MEMORY_REGION(0x3fce0000, 0x3fcee000, s3_late_rf_queue);
DMA_ATTR uint8_t rf_queue_tail[8192];
#elif PROBE_UPPER_FFT
SOC_RESERVE_MEMORY_REGION(0x3fce8000, 0x3fcf8000, s3_late_rf_queue);
#else
SOC_RESERVE_MEMORY_REGION(0x3fce4000, 0x3fcf4000, s3_late_rf_queue);
#endif
#else
SOC_RESERVE_MEMORY_REGION(0x3fce4000, 0x3fcec000, s3_late_rf_queue);
#endif
#if PROBE_ROM_SAFE
static uint8_t *const rf_packed_queue = (uint8_t *)0x3fce0000;
#elif PROBE_UPPER_FFT
static uint8_t *const rf_packed_queue = (uint8_t *)0x3fce8000;
#else
static uint8_t *const rf_packed_queue = (uint8_t *)0x3fce4000;
#endif
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
#if PROBE_UPPER_FFT
// One contiguous FFT slot replaces the late twiddle arena. Its peer and
// full twiddle table stay below the RF aperture, saving 16 KiB there.
#if PROBE_ROM_SAFE
SOC_RESERVE_MEMORY_REGION(0x3fcf0000, 0x3fcf8000, s3_late_fft_slot0);
#else
SOC_RESERVE_MEMORY_REGION(0x3fce0000, 0x3fce8000, s3_late_fft_slot0);
#endif
#if PROBE_RS_OFFLOAD
// DMA_ATTR requests four-byte alignment and can override the type's larger
// alignment. Repeat the 32-byte requirement on the actual variable.
DMA_ATTR __attribute__((aligned(32))) s3_mode_slot1 fft_mode_slot1;
#define fft_slot1 fft_mode_slot1.fft
#else
DMA_ATTR __attribute__((aligned(16))) uint8_t fft_slot1[32768];
#endif
#if PROBE_ROM_SAFE
static uint8_t *const fft_transfer_slots[2] = {(uint8_t *)0x3fcf0000, fft_slot1};
#else
static uint8_t *const fft_transfer_slots[2] = {(uint8_t *)0x3fce0000, fft_slot1};
#endif
#if PROBE_QUARTER_FFT
DRAM_ATTR __attribute__((aligned(16))) uint16_t fft_twiddle_reservation[2049];
#else
DRAM_ATTR __attribute__((aligned(16))) int16_t fft_twiddle_reservation[8192];
#endif
#else
DMA_ATTR uint8_t fft_transfer_slots[2][32768];
// IDF v5.5.1 exposes [0x3fce0000, 0x3fce9710) as internal heap at boot.
// Reserve a 16-KiB SIMD-aligned arena from that exact interval. It is never
// placed in ELF .data/.bss or used before app_main; startup code may use it.
// The tile kernel needs N/2 complex Q15 twiddles: 8192*2 = 16384 bytes.
SOC_RESERVE_MEMORY_REGION(0x3fce0000, 0x3fce4000, s3_fft_twiddle);
static int16_t *const fft_twiddle_reservation = (int16_t *)0x3fce0000;
#endif
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
#if PROBE_RS_OFFLOAD
    // Same physical late 32 KiB slot, selected only after T-mode DMA drains.
    // Link-only: retain code/layout; do not execute the receiver or solver.
    probe_keep ^= (uintptr_t)(s3_mode_slot0 *)0x3fcf0000 ^ (uintptr_t)&fft_mode_slot1;
    probe_keep ^= (uintptr_t)s3_rs_workspace_layout ^ (uintptr_t)&s3_rs_workspace_init ^
        (uintptr_t)&s3_rs_workspace_context ^ (uintptr_t)&s3_rs_rpc_syndromes ^
        (uintptr_t)&s3_rs_rpc_roots ^ (uintptr_t)&s3_rs_rpc_ack ^
        (uintptr_t)&s3_rs_rpc_crc ^ (uintptr_t)&s3_rs_solve ^ (uintptr_t)&s3_rs_magnitudes;
#endif
#if PROBE_ROM_SAFE
    probe_keep ^= (uintptr_t)rf_queue_tail;
    // The existing split-ring implementation retains all sixteen DMA pages.
    probe_keep ^= s3_ring_init_split(&transport_ring,rf_packed_queue,14,rf_queue_tail,2,1);
#endif
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
    probe_keep ^= (uintptr_t)&s3_ring_init_split;
    probe_keep ^= (uintptr_t)&s3_iq10_init ^ (uintptr_t)&s3_iq10_push ^ (uintptr_t)&s3_iq10_discard;
    probe_keep ^= (uintptr_t)&s3_rf_submit ^ (uintptr_t)&s3_rf_reap;
    probe_keep ^= (uintptr_t)&transport_credit ^ (uintptr_t)credit_status_response ^ (uintptr_t)credit_object_sizes;
    probe_keep ^= (uintptr_t)&s3_rf_submit_credited ^ (uintptr_t)&s3_spi_prepare_credit_status ^
        (uintptr_t)&s3_credit_init ^ (uintptr_t)&s3_credit_init_window ^ (uintptr_t)&s3_credit_status ^
        (uintptr_t)&s3_credit_reserve ^ (uintptr_t)&s3_credit_poison;
    probe_keep ^= (uintptr_t)&s3_t_rf_batch;
#if PROBE_QUARTER_FFT
    probe_keep ^= (uintptr_t)&s3_fft_reverse_tile ^ (uintptr_t)&s3_fft_stage_quarter_tile;
#else
    probe_keep ^= (uintptr_t)&s3_fft_reverse_tile ^ (uintptr_t)&s3_fft_stage_tile;
#endif
    probe_keep ^= (uintptr_t)&native_capture ^ (uintptr_t)&s3_native_start ^ (uintptr_t)&s3_native_poll ^
        (uintptr_t)&s3_native_stop ^ (uintptr_t)&s3_native_mmio;
    probe_keep ^= (uintptr_t)&capture_bridge ^ (uintptr_t)&s3_capture_init ^
        (uintptr_t)&s3_capture_accept ^ (uintptr_t)&s3_capture_reclaim ^ (uintptr_t)&s3_capture_step;
#elif PROBE_ZEROCOPY
    probe_keep ^= (uintptr_t)link_headers ^ (uintptr_t)link_descriptor_reserve;
#else
    probe_keep ^= (uintptr_t)link_staging;
#endif
#if PROBE_TERRESTRIAL
    probe_keep ^= (uintptr_t)fft_transfer_slots ^ (uintptr_t)fft_twiddle_reservation;
#if PROBE_ZEROCOPY
    // Explicit late initialization; no loader/static initializer touches it.
    for (unsigned i=0; i<(PROBE_QUARTER_FFT ? 2049u : 8192u); ++i) fft_twiddle_reservation[i] = 0;
#endif
#endif
    printf("Link-only probe: T=%d links=%d; RF/FFT/PHY are not running.\n",
           PROBE_TERRESTRIAL, PROBE_LINKS);
}

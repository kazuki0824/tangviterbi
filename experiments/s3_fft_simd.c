#include "s3_fft_simd.h"
#include "s3_fft_tiles.h"
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#include "esp_memory_utils.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#define HOT IRAM_ATTR
static portMUX_TYPE fft_context=portMUX_INITIALIZER_UNLOCKED;
#else
#define HOT
#endif
#include "s3_fft_simd_coefficients.inc"

/* Separate names prevent conflicts if the complete ESP-DSP library is linked.
 * No runtime initializer/allocation: the fixed table already has its bit order. */
uint8_t s3_pinned_fft_initialized=1;
int HOT s3_pinned_fft_power_of_two(int n) { return n>0 && !(n&(n-1)); }
extern int s3_pinned_fft_aes3(int16_t *data,int n,const int16_t *table);
static inline uint32_t cycles(void)
{
#ifdef __XTENSA__
    uint32_t value; __asm__ volatile("rsr.ccount %0":"=a"(value));return value;
#else
    return 0; /* Host oracle has no target cycle measurement. */
#endif
}
int HOT s3_fft_simd_run(int16_t *data,const int16_t *table,s3_fft_simd_measurement *m)
{
    uintptr_t d=(uintptr_t)data,t=(uintptr_t)table;
    if (!d || !t || ((d|t)&15) || d>UINTPTR_MAX-32768 || t>UINTPTR_MAX-16384 ||
        (d<t+16384 && t<d+32768)) return S3_FFT_SIMD_POINTER;
#ifdef ESP_PLATFORM
    /* Concrete policy: only core1 executes FFT. Core0 never waits on this
     * lock and continues RF polling. Local IRQ masking prevents a task/ISR
     * from replacing PIE registers while the pinned assembly uses them.
     * Board-level high-priority/NMI handlers must not use PIE instructions. */
    if(xPortGetCoreID()!=1 || !esp_ptr_internal(data) ||
       !esp_ptr_internal(data+16383) || !esp_ptr_internal(table) ||
       !esp_ptr_internal(table+8191)) return S3_FFT_SIMD_OWNER;
    portENTER_CRITICAL(&fft_context);
#endif
    uint32_t begin=cycles();
    int result=s3_pinned_fft_aes3(data,S3_FFT_SIMD_POINTS,table);
    uint32_t fft_end=cycles();
    if (result) {
#ifdef ESP_PLATFORM
        portEXIT_CRITICAL(&fft_context);
#endif
        return result;
    }
    /* Upstream kernel emits bit-reversed output. Reorder AFTER the kernel.
     * The old scalar DIT tiles instead require input reversal before stages. */
    s3_fft_reverse_tile(data,S3_FFT_SIMD_POINTS,0,S3_FFT_SIMD_POINTS);
    if(m) { m->fft_cycles=fft_end-begin; m->reorder_cycles=cycles()-fft_end; }
#ifdef ESP_PLATFORM
    portEXIT_CRITICAL(&fft_context);
#endif
    return S3_FFT_SIMD_OK;
}

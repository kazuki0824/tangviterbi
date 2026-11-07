#ifndef S3_CYCLE_CLOCK_H
#define S3_CYCLE_CLOCK_H
#include <stdbool.h>
#include <stdint.h>
/* Candidate common clock. One private state per pinned caller; no ISR may use
 * that state. Both CPUs must run continuously at 240 MHz after calibration.
 * Read intervals MUST be <2^32 cycles (17.895697066... s). A full missed wrap
 * cannot be detected from CCOUNT alone. No runtime WCET is asserted here.
 * U-error <= physical sampled time <= U, in the SDK clock's 240 MHz units.
 */
typedef struct {
 uint64_t upper;
 uint32_t last, error;
 bool valid;
} s3_cycle_clock_state;
/* Ordered startup observations: timer before, CCOUNT before, timer sample,
 * CCOUNT after, timer after. Timer observations are integer microseconds.
 * Startup may wait; there is no RF capture until calibration is accepted.
 * Recalibration is permitted only after all users/deadlines are quiesced.
 */
bool s3_cycle_clock_calibrate(s3_cycle_clock_state*,int64_t before_us,
 uint32_t before_count,int64_t sample_us,uint32_t after_count,int64_t after_us);
uint64_t s3_cycle_clock_advance(s3_cycle_clock_state*,uint32_t count);
#ifdef ESP_PLATFORM
bool s3_cycle_clock_init(s3_cycle_clock_state*);
uint64_t s3_cycle_clock_read(void*);
#endif
#endif

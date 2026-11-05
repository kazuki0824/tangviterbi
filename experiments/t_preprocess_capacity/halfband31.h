#ifndef HALFBAND31_H
#define HALFBAND31_H
#include <stddef.h>
#include <stdint.h>

/* Comparison candidate only. This is not an accepted receiver-quality contract.
 * Raw input: I in bits 0..9, Q in bits 10..19, signed10; upper bits ignored.
 * Coefficients are signed Q15. Output: sat16(accumulator >> shift), arithmetic
 * shift without rounding. The caller chooses shift from 0..31. shift=10 gives
 * no saturation for this coefficient table and any signed10 input, but has NOT
 * been accepted as equivalent to the receiver's currently unspecified rounding.
 */
enum { HB31_MAX_RAW = 1024, HB31_EVEN_HISTORY = 15, HB31_ODD_HISTORY = 8 };
typedef struct {
    _Alignas(4) int16_t even[HB31_EVEN_HISTORY * 2];
    int16_t odd[HB31_ODD_HISTORY * 2];
} hb31_state;
typedef struct {
    _Alignas(16) int16_t even[(HB31_MAX_RAW / 2 + HB31_EVEN_HISTORY + 1) * 2];
    _Alignas(16) int16_t odd[(HB31_MAX_RAW / 2 + HB31_ODD_HISTORY) * 2];
} hb31_workspace;

extern const int16_t hb31_coefficients[31];
extern const int16_t hb31_vectors[17][8];
void hb31_qacc4(const int16_t *even, const int16_t *odd,
    const int16_t coefficients[17][8], int16_t output[8], uint32_t shift);
/* Internal exact word copy. Nonoverlapping, 4-byte aligned, words > 0. */
void hb31_copy_words(void *destination, const void *source, size_t words);
/* History initially zero. raw_count must be a positive multiple of 8, <=1024.
 * state/raw are 4-byte aligned, output/workspace are 16-byte aligned. No aliasing
 * among raw, output, state and workspace. Returns complex output count, or 0
 * on invalid inputs without changing state or output. Caller owns PIE context.
 */
size_t hb31_process(hb31_state *state, hb31_workspace *workspace,
    const uint32_t *raw, size_t raw_count, int16_t *output, uint32_t shift);
#endif

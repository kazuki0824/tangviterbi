#include "halfband31.h"

const int16_t hb31_coefficients[31] = {
    -18, 0, 68, 0, -182, 0, 404, 0, -803, 0, 1533, 0, -3116, 0,
    10305, 16384, 10305, 0, -3116, 0, 1533, 0, -803, 0, 404, 0,
    -182, 0, 68, 0, -18
};
#define V8(c) {c,c,c,c,c,c,c,c}
_Alignas(16) const int16_t hb31_vectors[17][8] = {
    V8(-18), V8(68), V8(-182), V8(404), V8(-803), V8(1533),
    V8(-3116), V8(10305), V8(10305), V8(-3116), V8(1533),
    V8(-803), V8(404), V8(-182), V8(68), V8(-18), V8(16384)
};
#undef V8

static inline int16_t component10(uint32_t word) {
    /* The supported Xtensa/GCC and host/GCC targets use two's complement and
     * arithmetic signed right shift; left shift is deliberately unsigned. */
    return (int16_t)((int32_t)(word << 22) >> 22);
}

size_t hb31_process(hb31_state *state, hb31_workspace *workspace,
    const uint32_t *raw, size_t raw_count, int16_t *output, uint32_t shift) {
    if (!state || !workspace || !raw || !output || !raw_count ||
        raw_count > HB31_MAX_RAW || (raw_count & 7u) || shift > 31u ||
        (((uintptr_t)raw | (uintptr_t)state) & 3u) || ((uintptr_t)workspace & 15u) ||
        ((uintptr_t)output & 15u)) return 0;
    size_t count = raw_count / 2;
    hb31_copy_words(workspace->even, state->even, 15);
    hb31_copy_words(workspace->odd, state->odd, 8);
    for (size_t k = 0; k < count; ++k) {
        uint32_t even = raw[2*k], odd = raw[2*k+1];
        workspace->even[2*(k+15)] = component10(even);
        workspace->even[2*(k+15)+1] = component10(even >> 10);
        workspace->odd[2*(k+8)] = component10(odd);
        workspace->odd[2*(k+8)+1] = component10(odd >> 10);
    }
    workspace->even[2*(count+15)] = 0;
    workspace->even[2*(count+15)+1] = 0;
    for (size_t k = 0; k < count; k += 4) {
        hb31_qacc4(workspace->even + 2*k, workspace->odd + 2*k,
            hb31_vectors, output + 2*k, shift);
    }
    hb31_copy_words(state->even, workspace->even + 2*count, 15);
    hb31_copy_words(state->odd, workspace->odd + 2*count, 8);
    return count;
}

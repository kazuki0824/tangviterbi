#include "s3_fir_fused_reference.h"
static int32_t signed10(uint32_t x) {
    x &= 1023u;
    return (int32_t)(x ^ 512u) - 512;
}
int s3_fir_fused_reference(const uint32_t *words, const int16_t *coeff,
                         size_t count, int64_t *i_sum, int64_t *q_sum) {
    if (!words || !coeff || !i_sum || !q_sum || i_sum == q_sum || !count || count > 33)
        return 0;
    int64_t i = 0, q = 0;
    for (size_t k = 0; k < count; ++k) {
        uint32_t w = words[k];
        i += (int64_t)signed10(w) * coeff[k];
        q += (int64_t)signed10(w >> 10) * coeff[k];
    }
    *i_sum = i; *q_sum = q;
    return 1;
}

#include "accx_wrapper.h"
#include <stdint.h>

/* Host oracle hooks; never linked into the target object. Report contract
 * violations to the harness instead of aborting its remaining checks. */
accx_t_state accx_test_state;
int32_t accx_test_sums[16384][2];
uint32_t accx_test_heads[16384];
uint32_t accx_test_phases[16384];
size_t accx_test_calls;
unsigned accx_test_error;
const int16_t *accx_test_coeff_base;

void accx_test_reset(const int16_t *coeff) {
    accx_t_init(&accx_test_state);
    accx_test_coeff_base=coeff;
    accx_test_calls=0;
    accx_test_error=0;
}

#define REQUIRE(condition, code) do { \
    if (!(condition)) { accx_test_error=(code); out[0]=0; out[1]=0; return; } \
} while (0)

void s3_fir_accx_32(const int16_t *i, const int16_t *q,
                    const int16_t *coeff, int32_t out[2]) {
    REQUIRE(!accx_test_error, 1);
    REQUIRE(accx_test_calls < 16384, 2);
    REQUIRE(((uintptr_t)coeff & 15u) == 0, 3);
    REQUIRE((uintptr_t)coeff >= (uintptr_t)accx_test_coeff_base &&
            (uintptr_t)(coeff+32) <= (uintptr_t)(accx_test_coeff_base+1024), 4);
    REQUIRE(((uintptr_t)i & ~(uintptr_t)15) >= (uintptr_t)accx_test_state.i, 5);
    REQUIRE(((uintptr_t)q & ~(uintptr_t)15) >= (uintptr_t)accx_test_state.q, 6);
    REQUIRE(((uintptr_t)i & ~(uintptr_t)15)+80 <= (uintptr_t)(accx_test_state.i+64), 7);
    REQUIRE(((uintptr_t)q & ~(uintptr_t)15)+80 <= (uintptr_t)(accx_test_state.q+64), 8);
    REQUIRE(i-accx_test_state.i == q-accx_test_state.q, 9);
    int64_t a=0,b=0;
    for (unsigned k=0; k<32; ++k) {
        REQUIRE(i[k]>=-512 && i[k]<=511 && q[k]>=-512 && q[k]<=511, 10);
        a+=(int64_t)i[k]*coeff[k]; b+=(int64_t)q[k]*coeff[k];
    }
    REQUIRE(a>=INT32_MIN && a<=INT32_MAX && b>=INT32_MIN && b<=INT32_MAX, 11);
    out[0]=(int32_t)a; out[1]=(int32_t)b;
    accx_test_sums[accx_test_calls][0]=out[0];
    accx_test_sums[accx_test_calls][1]=out[1];
    accx_test_heads[accx_test_calls]=(uint32_t)(i-accx_test_state.i);
    accx_test_phases[accx_test_calls]=(uint32_t)(coeff-accx_test_coeff_base)/32;
    ++accx_test_calls;
}

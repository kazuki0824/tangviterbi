#include "s3_fir_qacc_prepare.h"
int s3_fir_qacc_prepare(const int16_t *i, const int16_t *q, size_t size,
    const int16_t *coeff, uint32_t up, uint32_t down, uint32_t taps,
    uint32_t first_output, int16_t *out_samples, int16_t *out_coeff) {
    if (!i || !q || !coeff || !out_samples || !out_coeff || !up || down<up ||
        (taps!=16 && taps!=32) || first_output>UINT32_MAX-3 ||
        (uint64_t)up*taps>SIZE_MAX/sizeof(int16_t)) return 0;
    uint64_t last=((uint64_t)first_output+3)*down/up;
    if (last>=size) return 0;
    for (uint32_t lane=0;lane<4;++lane) {
        uint64_t clock=((uint64_t)first_output+lane)*down;
        size_t newest=(size_t)(clock/up), phase=(size_t)(clock%up);
        for (uint32_t k=0;k<taps;++k) {
            size_t at=(size_t)k*8+lane*2;
            out_samples[at]=newest>=k ? i[newest-k] : 0;
            out_samples[at+1]=newest>=k ? q[newest-k] : 0;
            int16_t c=coeff[phase*taps+k];
            out_coeff[at]=c;out_coeff[at+1]=c;
        }
    }
    return 1;
}

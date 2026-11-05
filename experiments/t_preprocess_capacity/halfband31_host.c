#include "halfband31.h"
#include <string.h>
/* Host-only independent C backend for validating streaming/indexing. */
void hb31_qacc4(const int16_t *even, const int16_t *odd,
    const int16_t coefficients[17][8], int16_t output[8], uint32_t shift) {
    for (unsigned lane=0; lane<8; ++lane) {
        int64_t acc=(int64_t)odd[lane]*coefficients[16][lane];
        for (unsigned tap=0; tap<16; ++tap)
            acc+=(int64_t)even[2*tap+lane]*coefficients[tap][lane];
        int64_t den=(int64_t)1<<shift;
        int64_t value=acc>=0 ? acc/den : -((-acc+den-1)/den);
        output[lane]=(int16_t)(value>32767?32767:value< -32768?-32768:value);
    }
}
void hb31_copy_words(void *destination, const void *source, size_t words) {
    memcpy(destination, source, words * 4);
}

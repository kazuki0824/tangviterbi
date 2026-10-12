#include <stdbool.h>
static inline bool esp_ptr_internal(const void *p){return p!=0;}
static inline bool esp_ptr_dma_capable(const void *p){return p!=0;}

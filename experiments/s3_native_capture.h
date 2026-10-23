#ifndef S3_NATIVE_CAPTURE_H
#define S3_NATIVE_CAPTURE_H
#include "s3_capture_bridge.h"
// Zero-initialize s3_native_capture before first use. Start only after stop.
// The single RF owner calls poll and bridge step. Interrupts stay enabled.
// Hardware callback time must include every MMIO/write/sentinel operation.
// Native S3 backend is experimental: undocumented RF ABI needs board validation.
typedef struct {
 uint32_t (*read)(void*,uint32_t);
 void (*write)(void*,uint32_t,uint32_t);
 uint32_t (*cycles)(void*);
 uint32_t *(*bank)(void*,unsigned);
 void *ctx;
} s3_native_io;
/* Coordinator-owned destination for validated RF bank handoff. Callbacks must
 * include their cost in RF poll WCET. accept failure stops capture; no drops.
 */
typedef struct {
 void *ctx;
 bool (*healthy)(void*);
 bool (*available)(void*,unsigned);
 bool (*reclaim)(void*,unsigned);
 bool (*accept)(void*,unsigned,const uint32_t*,unsigned,unsigned,uint64_t,uint64_t,uint64_t);
} s3_native_sink;
typedef struct {
 s3_native_io io; s3_capture_bridge *bridge; s3_native_sink sink;
 uint64_t now,index,switched; uint32_t last_clock,saved,ctrl,w0,expected,write_index;
 uint32_t start[3],end[3];
 unsigned active,unit,cpp; bool running,prepared,settling; unsigned fault;
} s3_native_capture;
bool s3_native_start(s3_native_capture*,s3_capture_bridge*,s3_native_io,unsigned rate_msps);
bool s3_native_start_sink(s3_native_capture*,s3_native_sink,s3_native_io,unsigned rate_msps);
bool s3_native_poll(s3_native_capture*);
void s3_native_stop(s3_native_capture*);
#ifdef ESP_PLATFORM
s3_native_io s3_native_mmio(void);
#endif
#endif

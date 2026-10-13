#ifndef S3_MODE_SWITCH_H
#define S3_MODE_SWITCH_H
#include <stdbool.h>
#include <stdint.h>
enum s3_mode {S3_MODE_T=0,S3_MODE_S=1,S3_MODE_RECOVERY=2};
enum s3_switch_state {S3_SWITCH_RUNNING,S3_SWITCH_DRAIN,S3_SWITCH_BOOT,S3_SWITCH_EPOCH,S3_SWITCH_LOCK,S3_SWITCH_ENABLE,S3_SWITCH_FAULT};
/* Board external SPI NOR only: T -> S -> recovery -> T. Background
 * programming is not a streaming runtime transport. A pulse callback must
 * implement the board's 1.8-V RECONFIG_N interface and validated pulse time.
 * drain must join workers AND finish every DMA before reporting success.
 * identity must read the actually booted image, not infer it from hop count.
 */
typedef struct {
 bool (*stop)(void *);
 int (*drain)(void *); /* -1 failure, 0 pending, 1 all owners/DMAs stopped */
 bool (*pulse)(void *);
 int (*identity)(void *,enum s3_mode *);
 int (*epoch)(void *,uint16_t);
 bool (*tune)(void *,enum s3_mode);
 int (*locked)(void *);
 int (*enable)(void *); /* -1 fault, 0 pending, 1 actual FPGA enable ACK */
 void *ctx;
} s3_switch_io;
typedef struct {
 s3_switch_io io;enum s3_mode current,target,expected;
 enum s3_switch_state state;uint16_t epoch;unsigned hops;
 uint64_t deadline;
} s3_mode_switch;
bool s3_mode_switch_init(s3_mode_switch *,s3_switch_io,enum s3_mode,uint16_t);
bool s3_mode_switch_request(s3_mode_switch *,enum s3_mode,uint64_t now_us);
bool s3_mode_switch_step(s3_mode_switch *,uint64_t now_us);
#endif

#ifndef S3_RS_OFFLOAD_H
#define S3_RS_OFFLOAD_H
#include <stdint.h>
/* Experimental RS split solver. Not integrated with RF/RTOS/SPI. All tables
 * must live in internal SRAM for a future target timing claim. */
typedef struct {
 uint8_t exp[512],log[256],step[8][256];
 uint32_t mul_calls,mul_nonzero,div_calls,chien_steps;
} s3_rs_tables;
typedef struct { uint8_t lambda[17],omega[16],degree; } s3_rs_solution;
void s3_rs_tables_init(s3_rs_tables *t);
int s3_rs_solve(s3_rs_tables *t,const uint8_t syndrome[16],s3_rs_solution *s);
int s3_rs_chien(s3_rs_tables *t,const s3_rs_solution *s,uint8_t positions[8]);
int s3_rs_magnitudes(s3_rs_tables *t,const s3_rs_solution *s,
                    const uint8_t *positions,unsigned count,uint8_t magnitudes[8]);
#endif

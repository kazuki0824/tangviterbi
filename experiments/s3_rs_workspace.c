#include "s3_rs_workspace.h"
#include <stddef.h>
_Static_assert(sizeof(s3_rs_slot0)<=32768,"S slot0 overflow");
_Static_assert(sizeof(s3_rs_slot1)<=32768,"S slot1 overflow");
_Static_assert(sizeof(s3_mode_slot0)==32768 && sizeof(s3_mode_slot1)==32768,"FFT union changed");
_Static_assert(offsetof(s3_rs_slot0,rx)%32==0 && offsetof(s3_rs_slot0,tx)%32==0,"DMA alignment");
_Static_assert(offsetof(s3_rs_slot1,rx)%32==0 && offsetof(s3_rs_slot1,tx)%32==0,"second DMA alignment");
const uint32_t s3_rs_workspace_layout[14]={
 sizeof(s3_mode_slot0),sizeof(s3_mode_slot1),sizeof(s3_rs_slot0),sizeof(s3_rs_slot1),
 offsetof(s3_rs_slot0,contexts),offsetof(s3_rs_slot0,crc),offsetof(s3_rs_slot0,rx),offsetof(s3_rs_slot0,tx),
 offsetof(s3_rs_slot1,contexts),offsetof(s3_rs_slot1,tables),offsetof(s3_rs_slot1,rx),offsetof(s3_rs_slot1,tx),
 sizeof(s3_rs_rpc_context),sizeof(s3_rs_tables)
};
void s3_rs_workspace_init(s3_mode_slot0 *a,s3_mode_slot1 *b) {
 for(unsigned n=0;n<3;n++)s3_rs_rpc_reset(&a->rs.contexts[n]);
 for(unsigned n=0;n<2;n++)s3_rs_rpc_reset(&b->rs.contexts[n]);
 s3_rs_rpc_crc_init(a->rs.crc);s3_rs_tables_init(&b->rs.tables);
}
s3_rs_rpc_context *s3_rs_workspace_context(s3_mode_slot0 *a,s3_mode_slot1 *b,unsigned index) {
 if(index<3)return &a->rs.contexts[index];
 if(index<5)return &b->rs.contexts[index-3];
 return NULL;
}

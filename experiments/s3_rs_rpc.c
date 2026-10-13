/* Experimental whole-batch RPC for CPU BM/Omega/Forney, FPGA Chien.
 * Fixed little-endian v1 page header: "RS", version, kind, epoch16,
 * count16 (204), batch32, CRC32/ISO-HDLC. CRC field reads as zero during
 * calculation. Every byte including zero tail padding is protected. */
#include "s3_rs_rpc.h"
#include <string.h>
_Static_assert(sizeof(s3_rs_rpc_context)==7148,"Update the internal-SRAM budget for this ABI");
static unsigned S3_RS_HOT get16(const uint8_t *p) {return p[0]|((unsigned)p[1]<<8);}
static uint32_t S3_RS_HOT get32(const uint8_t *p) {
 return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void S3_RS_HOT put16(uint8_t *p,unsigned n) {p[0]=(uint8_t)n;p[1]=(uint8_t)(n>>8);}
static void S3_RS_HOT put32(uint8_t *p,uint32_t n) {for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(n>>(8*i));}
void S3_RS_HOT s3_rs_rpc_crc_init(uint32_t table[256]) {
 for(unsigned n=0;n<256;n++){
  uint32_t x=n;
  for(unsigned b=0;b<8;b++)x=(x>>1)^((x&1)?UINT32_C(0xedb88320):0);
  table[n]=x;
 }
}
uint32_t S3_RS_HOT s3_rs_rpc_crc(const uint32_t table[256],const uint8_t page[4096]) {
 uint32_t x=UINT32_MAX;
 for(unsigned n=0;n<4096;n++){
  uint8_t b=(n>=12&&n<16)?0:page[n];
  x=(x>>8)^table[(x^b)&255];
 }
 return x^UINT32_MAX;
}
void S3_RS_HOT s3_rs_rpc_reset(s3_rs_rpc_context *context) {memset(context,0,sizeof(*context));}
static int S3_RS_HOT header(const uint32_t crc[256],const uint8_t *rx,
 unsigned kind,unsigned size,uint16_t epoch,uint32_t batch) {
 if(rx[0]!='R'||rx[1]!='S'||rx[2]!=1||rx[3]!=kind||get16(rx+4)!=epoch||
    get16(rx+6)!=204||get32(rx+8)!=batch||get32(rx+12)!=s3_rs_rpc_crc(crc,rx))return 0;
 for(unsigned i=16+204*size;i<4096;i++)if(rx[i])return 0;
 for(unsigned i=0;i<204;i++)if(get16(rx+16+i*size)!=i)return 0;
 return 1;
}
static void S3_RS_HOT begin(uint8_t *tx,const s3_rs_rpc_context *c,unsigned kind) {
 memset(tx,0,4096);tx[0]='R';tx[1]='S';tx[2]=1;tx[3]=(uint8_t)kind;
 put16(tx+4,c->epoch);put16(tx+6,204);put32(tx+8,c->batch);
}
int S3_RS_HOT s3_rs_rpc_syndromes(s3_rs_tables *tables,const uint32_t crc[256],
 s3_rs_rpc_context *context,uint16_t epoch,uint32_t batch,
 const uint8_t rx[4096],uint8_t tx[4096]) {
 if(rx==tx||context->phase!=S3_RS_RPC_FREE||
    !header(crc,rx,S3_RS_RPC_SYNDROME,19,epoch,batch))return 0;
 /* Validate the WHOLE page before modifying persistent state or output. */
 for(unsigned i=0;i<204;i++){
  const uint8_t *r=rx+16+i*19;
  if(r[2]>1)return 0;
  if(r[2])for(unsigned j=3;j<19;j++)if(r[j])return 0;
 }
 context->epoch=epoch;context->batch=batch;begin(tx,context,S3_RS_RPC_LAMBDA);
 for(unsigned i=0;i<204;i++){
  const uint8_t *r=rx+16+i*19;uint8_t *w=tx+16+i*13;
  put16(w,i);
  context->failed[i]=r[2]||!s3_rs_solve(tables,r+3,&context->solution[i]);
  w[2]=context->failed[i];
  if(!w[2]){w[3]=context->solution[i].degree;memcpy(w+4,context->solution[i].lambda,9);}
 }
 put32(tx+12,s3_rs_rpc_crc(crc,tx));context->phase=S3_RS_RPC_WAIT_ROOTS;
 return 1;
}
int S3_RS_HOT s3_rs_rpc_roots(s3_rs_tables *tables,const uint32_t crc[256],
 s3_rs_rpc_context *context,const uint8_t rx[4096],uint8_t tx[4096]) {
 if(rx==tx||context->phase!=S3_RS_RPC_WAIT_ROOTS||
    !header(crc,rx,S3_RS_RPC_ROOTS,12,context->epoch,context->batch))return 0;
 for(unsigned i=0;i<204;i++){
  const uint8_t *r=rx+16+i*12;unsigned n=r[2];
  if(r[11]||(n>8&&n!=255)||(context->failed[i]&&n!=255))return 0;
  if(n==255)n=0;
  for(unsigned j=0;j<n;j++)if(r[3+j]>=204||(j&&r[3+j]<=r[2+j]))return 0;
  for(unsigned j=n;j<8;j++)if(r[3+j])return 0;
 }
 begin(tx,context,S3_RS_RPC_MAGNITUDES);
 for(unsigned i=0;i<204;i++){
  const uint8_t *r=rx+16+i*12;uint8_t *w=tx+16+i*12;
  put16(w,i);
  w[2]=r[2]==255||context->failed[i]||
   !s3_rs_magnitudes(tables,&context->solution[i],r+3,r[2],w+3);
  if(w[2])memset(w+3,0,8); /* Never publish partially computed corrections. */
 }
 put32(tx+12,s3_rs_rpc_crc(crc,tx));context->phase=S3_RS_RPC_WAIT_ACK;
 return 1;
}
int S3_RS_HOT s3_rs_rpc_ack(s3_rs_rpc_context *context,uint16_t epoch,uint32_t batch) {
 if(context->phase!=S3_RS_RPC_WAIT_ACK||context->epoch!=epoch||context->batch!=batch)return 0;
 context->phase=S3_RS_RPC_FREE;return 1;
}

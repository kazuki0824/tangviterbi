#include "s3_parallel_pack.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static _Alignas(16) uint8_t storage[4][32768];
static unsigned long cases;
static void verify(uint64_t start,unsigned count,const unsigned *order) {
 s3_parallel_pack p;uint8_t *buffers[4]={storage[0],storage[1],storage[2],storage[3]};
 assert(s3_pp_init(&p,buffers)==S3_PP_OK);
 p.submitted=p.retired=start;p.published=(start+count)*S3_PP_TX_BYTES;
 for(unsigned i=0;i<count;i++){
  uint64_t seq;const uint8_t *data;assert(s3_pp_take(&p,&seq,&data)==S3_PP_OK);
  assert(seq==start+i);uint64_t offset=seq*S3_PP_TX_BYTES;
  assert(data==buffers[(offset/S3_PP_CHUNK)%4]+offset%S3_PP_CHUNK);
 }
 uint64_t seq;const uint8_t *data;assert(s3_pp_take(&p,&seq,&data)==S3_PP_EMPTY);
 bool done[S3_PP_LEASES];memset(done,0,sizeof(done));unsigned retired=0;
 for(unsigned i=0;i<count;i++){
  unsigned n=order[i];assert(s3_pp_complete(&p,start+n)==S3_PP_OK);done[n]=true;
  while(retired<count&&done[retired])retired++;
  assert(p.retired==start+retired);
  uint64_t before=p.retired;assert(s3_pp_complete(&p,start+n)==S3_PP_STALE);assert(p.retired==before);
 }
 assert(p.retired==p.submitted);cases++;
}
static void permute(uint64_t start,unsigned count,unsigned pos,unsigned *order,unsigned used){
 if(pos==count){verify(start,count,order);return;}
 for(unsigned i=0;i<count;i++)if(!(used&(1u<<i))){order[pos]=i;permute(start,count,pos+1,order,used|(1u<<i));}
}
int main(void){
 const uint64_t starts[]={0,1,(UINT64_C(1)<<32)-8,(UINT64_C(1)<<32)-4,(UINT64_C(1)<<32)-1,UINT64_C(1)<<32,(UINT64_C(1)<<32)+1,UINT64_MAX/S3_PP_TX_BYTES-8};
 unsigned order[S3_PP_LEASES];
 for(unsigned k=0;k<sizeof(starts)/sizeof(starts[0]);k++)for(unsigned n=1;n<=S3_PP_LEASES;n++)permute(starts[k],n,0,order,0);
 printf("{\"transfer_bytes\":%u,\"leases\":%u,\"start_values\":8,\"completion_orders\":%lu}\n",S3_PP_TX_BYTES,S3_PP_LEASES,cases);
}

/* Exercise the actual private fill, including words outside its write set. */
#include "s3_native_capture.c"
#include <assert.h>
#include <stdio.h>
static uint32_t guarded[16386];
static unsigned bank_calls;
static uint32_t *get_bank(void *ctx,unsigned b){assert(ctx==guarded);assert(b==2);++bank_calls;return guarded+1;}
int main(void){
 s3_native_capture s={0};s.io.bank=get_bank;s.io.ctx=guarded;
 unsigned lengths[]={0,1,2,3072,4096,16384,16385};
 unsigned cases=0;
 for(unsigned at=0;at<16384;++at)for(unsigned j=0;j<sizeof(lengths)/sizeof(*lengths);++j){
  unsigned n=lengths[j];
  for(unsigned k=0;k<16386;++k)guarded[k]=k;
  unsigned before=bank_calls;
  fill(&s,2,at,n);
  assert(bank_calls==before+1);
  assert(guarded[0]==0&&guarded[16385]==16385);
  for(unsigned k=0;k<16384;++k){
   unsigned distance=(k+16384-at)%16384;
   assert(guarded[k+1]==(distance<n?SENTINEL:k+1));
  }
  ++cases;
 }
 /* Noncanonical origin is masked before the first write. */
 fill(&s,2,UINT32_MAX,2);assert(guarded[16384]==SENTINEL&&guarded[1]==SENTINEL);
 printf("PASS actual fill: %u cases, all ring origins, unchanged words and guard words checked\n",cases+1);
}

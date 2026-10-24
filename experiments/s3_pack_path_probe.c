/* Functional execution/counting harness. Artificial zero clock, synchronous
 * workers and immediate DMA completion: NOT a real-time execution schedule. */
#include "s3_parallel_pack.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
unsigned long long s3_audit_stats[2][5];
unsigned s3_audit_owner;
static _Alignas(16) uint8_t data[4][S3_PP_CHUNK];
static uint32_t source[3][S3_PP_WORDS];
static s3_parallel_pack p;
static uint32_t sample(uint64_t n) {return (uint32_t)(n*65497u+(n>>11)*713u+71u)&0xfffffu;}
static uint8_t expected(uint64_t byte) {
 uint64_t pair=byte/5,bits=sample(2*pair)|((uint64_t)sample(2*pair+1)<<20);
 return (uint8_t)(bits>>(8*(byte%5)));
}
static uint64_t clock_zero(void *ctx) {(void)ctx;++s3_audit_stats[s3_audit_owner][4];return 0;}
int main(void) {
 const unsigned sizes[]={12288,12289,14288},starts[]={0,16380},slices[]={64,128,512,1024};
 puts("[");unsigned row=0;
 for(unsigned c=0;c<3;++c)for(unsigned f=0;f<2;++f)for(unsigned z=0;z<4;++z) {
  uint8_t*buffers[]={data[0],data[1],data[2],data[3]};assert(s3_pp_init(&p,buffers)==S3_PP_OK);
  memset(s3_audit_stats,0,sizeof(s3_audit_stats));unsigned count=sizes[c];uint64_t seq=0;
  for(unsigned bank=0;bank<64;++bank) {
   unsigned b=bank%3,first=starts[f];
   assert(s3_pp_reclaim(&p,b)==S3_PP_OK);
   for(unsigned k=0;k<count;++k)source[b][(first+k)%S3_PP_WORDS]=sample(seq+k)|0xabc00000u;
   uint64_t before=p.published;
   assert(s3_pp_accept(&p,b,source[b],first,count,seq,0,100)==S3_PP_OK);seq+=count;
   for(unsigned w=0;w<2;++w) {
    s3_audit_owner=w;
    while(p.banks[b].jobs[w].cursor<p.banks[b].jobs[w].end) {
     unsigned processed=0;++s3_audit_stats[w][3];
     assert(s3_pp_step_clocked(&p,w,slices[z],clock_zero,NULL,1,&processed)==S3_PP_OK);
     assert(processed && processed<=slices[z]);
    }
   }
   assert(s3_pp_collect(&p,0)==S3_PP_OK);
   for(uint64_t byte=before;byte<p.published;++byte)
    assert(data[(byte/S3_PP_CHUNK)%4][byte%S3_PP_CHUNK]==expected(byte));
   uint64_t ticket;const uint8_t*payload;
   while(s3_pp_take(&p,&ticket,&payload)==S3_PP_OK)assert(s3_pp_complete(&p,ticket)==S3_PP_OK);
  }
  unsigned long long pairs=0;
  for(unsigned w=0;w<2;++w){pairs+=4*s3_audit_stats[w][1]+s3_audit_stats[w][2];assert(s3_audit_stats[w][4]==2*s3_audit_stats[w][3]);}
  assert(pairs==seq/2 && p.published==pairs*5);
  printf("%s{\"bank_samples\":%u,\"first\":%u,\"slice_pairs\":%u,\"banks\":64,\"stats\":[",row++?",\n":"",count,starts[f],slices[z]);
  for(unsigned w=0;w<2;++w)printf("%s[%llu,%llu,%llu,%llu,%llu]",w?",":"",s3_audit_stats[w][0],s3_audit_stats[w][1],s3_audit_stats[w][2],s3_audit_stats[w][3],s3_audit_stats[w][4]);
  printf("]}");
 }
 puts("\n]");
}

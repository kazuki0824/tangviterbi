#include "s3_parallel_pack.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static _Alignas(16) unsigned char data[4][S3_PP_CHUNK], expected[4][S3_PP_CHUNK];
static uint32_t source[S3_PP_WORDS];
static s3_parallel_pack p;
static uint32_t sample(unsigned first,unsigned index,unsigned prefix) {
 if(prefix) {if(!index)return 0x98765;--index;}
 return source[(first+index)%S3_PP_WORDS]&0xfffff;
}
int main(void) {
 const unsigned starts[]={0,1,7,8191,16375,16376,16377,16382,16383};
 const unsigned offsets[]={0,1,2,3,32748,32749,32767,32768,131052,131071};
 const unsigned lengths[]={1,3,4,5,16,127,1024};
 const unsigned slices[]={1,3,4,5,127,1024};
 unsigned cases=0;
 for(unsigned i=0;i<S3_PP_WORDS;++i)source[i]=0xabc00000u|((i*73129u+123u)&0xfffff);
 for(unsigned f=0;f<sizeof(starts)/sizeof(*starts);++f)
 for(unsigned o=0;o<sizeof(offsets)/sizeof(*offsets);++o)
 for(unsigned prefix=0;prefix<2;++prefix)
 for(unsigned skip=0;skip<2;++skip)
 for(unsigned n=0;n<sizeof(lengths)/sizeof(*lengths);++n)
 for(unsigned z=0;z<sizeof(slices)/sizeof(*slices);++z) {
  uint8_t *buffers[]={data[0],data[1],data[2],data[3]};
  assert(s3_pp_init(&p,buffers)==S3_PP_OK);
  memset(data,0xcc,sizeof(data));memset(expected,0xcc,sizeof(expected));
  s3_pp_bank*b=&p.banks[0];b->words=source;b->first=starts[f];b->has_prefix=prefix;
  b->prefix=0x98765;b->owned=true;b->deadline=100;
  b->output=offsets[o];while(b->output%5)b->output+=sizeof(data);
  unsigned begin=skip?3:0,end=begin+lengths[n];b->pairs=end;
  b->jobs[0].begin=begin;b->jobs[0].cursor=begin;b->jobs[0].end=end;
  atomic_store(&b->jobs[0].state,1);
  for(unsigned pair=begin;pair<end;++pair) {
   uint64_t bits=sample(b->first,2*pair,prefix)|((uint64_t)sample(b->first,2*pair+1,prefix)<<20);
   for(unsigned byte=0;byte<5;++byte) {
    unsigned at=(unsigned)((b->output+pair*5+byte)%sizeof(data));
    expected[at/S3_PP_CHUNK][at%S3_PP_CHUNK]=(uint8_t)(bits>>(byte*8));
   }
  }
  unsigned count=0;
  while(b->jobs[0].cursor<end) {
   unsigned processed=0;
   assert(s3_pp_step(&p,0,slices[z],0,1,&processed)==S3_PP_OK);
   assert(processed && processed<=slices[z]);count+=processed;
  }
  assert(count==lengths[n] && b->owned && !atomic_load(&p.fault));
  assert(!memcmp(data,expected,sizeof(data)));
  unsigned processed=123;assert(s3_pp_step(&p,0,1,0,1,&processed)==S3_PP_EMPTY && processed==0);
  ++cases;
 }
 printf("PASS %u input-wrap/output-wrap/prefix/worker-offset/slice cases; full output and untouched bytes checked\n",cases);
}

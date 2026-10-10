/* Roots alpha^0..15, GF(256)/0x11d, 51 leading-zero shortening.
 * No received samples or codeword bytes cross this solver's interface. */
#include "s3_rs_offload.h"
#include <string.h>
#ifdef S3_RS_PROFILE
#define COUNT(t,field) (++(t)->field)
#else
#define COUNT(t,field) ((void)0)
#endif
static uint8_t S3_RS_HOT mul(s3_rs_tables *t,uint8_t a,uint8_t b) {
 COUNT(t,mul_calls);
 if(!a || !b)return 0;
 COUNT(t,mul_nonzero);
 return t->exp[(unsigned)t->log[a]+t->log[b]];
}
static uint8_t S3_RS_HOT div_nonzero(s3_rs_tables *t,uint8_t a,uint8_t b) {
 COUNT(t,div_calls);
 return a?t->exp[255u+t->log[a]-t->log[b]]:0;
}
void S3_RS_HOT s3_rs_tables_init(s3_rs_tables *t) {
 memset(t,0,sizeof(*t));unsigned x=1;
 for(unsigned n=0;n<255;n++){
  t->exp[n]=(uint8_t)x;t->log[x]=(uint8_t)n;
  x<<=1;if(x&256)x^=0x11d;
 }
 for(unsigned n=255;n<512;n++)t->exp[n]=t->exp[n-255];
 for(unsigned row=0;row<8;row++)for(unsigned a=1;a<256;a++)
  t->step[row][a]=t->exp[(unsigned)t->log[a]+row+1];
}
int S3_RS_HOT s3_rs_solve(s3_rs_tables *t,const uint8_t syndrome[16],s3_rs_solution *s) {
 uint8_t bpoly[17]={1},previous[17],b=1;
 unsigned degree=0,shift=1;
 memset(s,0,sizeof(*s));s->lambda[0]=1;
 for(unsigned n=0;n<16;n++){
  uint8_t d=syndrome[n];
  for(unsigned i=1;i<=degree && i<=n;i++)d^=mul(t,s->lambda[i],syndrome[n-i]);
  if(!d){shift++;continue;}
  memcpy(previous,s->lambda,sizeof(previous));
  uint8_t coefficient=div_nonzero(t,d,b);
  for(unsigned i=0;i+shift<17;i++)s->lambda[i+shift]^=mul(t,coefficient,bpoly[i]);
  if(2*degree<=n){
   degree=n+1-degree;
   if(degree>8)return 0;
   memcpy(bpoly,previous,sizeof(bpoly));b=d;shift=1;
  }else shift++;
 }
 s->degree=(uint8_t)degree;
 for(unsigned n=0;n<16;n++)
  for(unsigned i=0;i<=degree && i<=n;i++)s->omega[n]^=mul(t,s->lambda[i],syndrome[n-i]);
 return 1;
}
int S3_RS_HOT s3_rs_chien(s3_rs_tables *t,const s3_rs_solution *s,uint8_t positions[8]) {
 if(s->degree>8)return -1;
 uint8_t term[8]={0};unsigned count=0;
 for(unsigned i=0;i<s->degree;i++)term[i]=mul(t,s->lambda[i+1],t->exp[(52*(i+1))%255]);
 for(unsigned p=0;p<204;p++){
  uint8_t v=s->lambda[0];
  for(unsigned i=0;i<s->degree;i++)v^=term[i];
  if(!v){if(count==8)return -1;positions[count++]=(uint8_t)p;}
  for(unsigned i=0;i<s->degree;i++){
   term[i]=t->step[i][term[i]];COUNT(t,chien_steps);
  }
 }
 return count==s->degree?(int)count:-1;
}
int S3_RS_HOT s3_rs_magnitudes(s3_rs_tables *t,const s3_rs_solution *s,
                    const uint8_t *positions,unsigned count,uint8_t magnitudes[8]) {
 if(s->degree>8 || count!=s->degree)return 0;
 for(unsigned e=0;e<count;e++){
  unsigned p=positions[e];if(p>=204)return 0;
  for(unsigned earlier=0;earlier<e;earlier++)if(positions[earlier]==p)return 0;
  uint8_t x=t->exp[(p+52)%255],locator=s->lambda[s->degree],omega=0,derivative=0;
  for(unsigned i=s->degree;i>0;i--)locator=mul(t,locator,x)^s->lambda[i-1];
  if(locator)return 0; /* validate positions supplied by a future FPGA */
  for(unsigned i=16;i>0;i--)omega=mul(t,omega,x)^s->omega[i-1];
  uint8_t x2=mul(t,x,x);
  for(int i=7;i>=1;i-=2)derivative=mul(t,derivative,x2)^s->lambda[i];
  uint8_t denominator=mul(t,derivative,x);
  if(!denominator)return 0;
  magnitudes[e]=div_nonzero(t,omega,denominator);
 }
 return 1;
}

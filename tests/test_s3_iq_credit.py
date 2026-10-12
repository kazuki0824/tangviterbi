"""Ordered IQ publication credit, including simultaneous publication and wrap."""
from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class CreditTest(unittest.TestCase):
 def test_credit_lifetime_and_fail_stop(self):
  out=ROOT/'build/s3-iq-credit';out.mkdir(parents=True,exist_ok=True)
  (out/'test.c').write_text(r'''
#include "s3_iq_credit.h"
#include <assert.h>
#include <stdio.h>
static unsigned published,reads;static bool unstable;
static unsigned gray(void *ctx){(void)ctx;unsigned v=published&3,g=v^(v>>1);if(unstable&&(++reads&1))g^=1;return g;}
int main(void){s3_iq_credit s;
 assert(!s3_iq_credit_init(&s,0,gray,0));assert(s3_iq_credit_init(&s,17,gray,0));
 assert(s3_iq_credit_take(&s,17,0)==0);published=2;
 assert(s3_iq_credit_take(&s,17,0)==1&&s.available==1);
 unstable=true;assert(s3_iq_credit_take(&s,17,4096)==0&&s.available==1);unstable=false;
 assert(s3_iq_credit_take(&s,17,4096)==1&&!s.available);
 for(unsigned page=2;page<10000;++page){assert(s3_iq_credit_take(&s,17,page*4096)==0);++published;assert(s3_iq_credit_take(&s,17,page*4096)==1);}
 assert(s.offset==40960000&&s.last==0&&!s.fault);
 assert(s3_iq_credit_take(&s,18,s.offset)==-1&&s.fault);
 published=0;assert(s3_iq_credit_init(&s,17,gray,0));published=3;
 assert(s3_iq_credit_take(&s,17,0)==-1&&s.fault);
 published=0;assert(s3_iq_credit_init(&s,17,gray,0));++published;
 assert(s3_iq_credit_take(&s,17,4096)==-1&&s.fault);
 puts("PASS 10000 exact IQ page credits, two publications, Gray wrap, unstable retry, epoch/offset/overpublication fail-stop");
}''')
  subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-Iexperiments','experiments/s3_iq_credit.c',str(out/'test.c'),'-o',str(out/'sim')],cwd=ROOT,check=True)
  r=subprocess.run([str(out/'sim')],capture_output=True,text=True,timeout=15)
  (out/'simulation.log').write_text(r.stdout+r.stderr);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()

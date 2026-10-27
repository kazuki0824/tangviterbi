"""Execute pinned req_core with an interleaving hook after atomic OR."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_s3_spi_lock_primitives import function

ROOT=Path(__file__).resolve().parents[1]


class RequestEnableTest(unittest.TestCase):
    def test_actual_request_uses_pre_or_status_after_intervening_isr(self):
        source=(ROOT/'reports/s3-spi-wait-audit/sources/spi_bus_lock.c').read_text()
        shim=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#define SPI_BUSLOCK_ATTR
#define DEV_REQ_MASK(d) 1u
#define DEV_BG_MASK(d) 3u
typedef struct device device;
typedef struct {unsigned status;device *acquiring_dev;bool acq_dev_bg_active;} spi_bus_lock_t;
struct device {spi_bus_lock_t *parent;};
typedef device spi_bus_lock_dev_t;
static unsigned enables,ors,hook;
static uint32_t lock_status_fetch_set(spi_bus_lock_t*l,unsigned mask){
 unsigned old=l->status;l->status|=mask;++ors;
 /* Emulate an ISR's status operations after OR has linearized, but before
    req_core tests its saved old value. This is not an ISR timing model. */
 if(hook)l->status=0;
 return old;
}
static void bg_enable(spi_bus_lock_t*l){(void)l;++enables;}
'''
        main=r'''
int main(void){
 for(unsigned old=0;old<4;++old)for(hook=0;hook<2;++hook){
  spi_bus_lock_t lock={.status=old};device dev={&lock};
  enables=ors=0;req_core(&dev);
  assert(ors==1);assert(enables==(old==0));
  assert(lock.status==(hook?0:(old|1)));
 }
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'request.c').write_text(shim+function(source,'req_core')+main)
            build=subprocess.run(['cc','-std=c11','-Wall','-Werror','-fsanitize=undefined',
                str(root/'request.c'),'-o',str(root/'request')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            subprocess.run([str(root/'request')],check=True)


if __name__=='__main__':unittest.main()

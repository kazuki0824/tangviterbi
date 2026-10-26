"""Compile exact pinned SDK primitive bodies with a sequential atomic shim.
This verifies branch/bit semantics only, not Xtensa atomic timing or concurrency.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

def function(text,name):
    match=re.search(r'[^\n]*\b'+name+r'\([^;]*?\)\n\{',text)
    if not match:raise AssertionError(name)
    start=match.start();at=match.end();depth=1
    while depth:
        depth+=(text[at]=='{')-(text[at]=='}');at+=1
    return text[start:at]

class SDKPrimitivesTest(unittest.TestCase):
    def test_actual_sdk_req_pend_and_wip_exit(self):
        text=(ROOT/'reports/s3-spi-wait-audit/sources/spi_bus_lock.c').read_text()
        code=r'''
#include <stdbool.h>
#include <stdint.h>
#include <assert.h>
#define SPI_BUS_LOCK_ISR_ATTR
#define IRAM_ATTR
#define BUS_LOCK_DEBUG_EXECUTE_CHECK(x) ((void)0)
#define REQ_MASK 1u
#define PEND_MASK 2u
#define BG_MASK 3u
#define REQ_SHIFT 0
#define PENDING_SHIFT 1
#define DEV_BG_MASK(x) 3u
typedef int BaseType_t;
typedef struct spi_bus_lock_dev spi_bus_lock_dev_t;
typedef struct {unsigned status;spi_bus_lock_dev_t* acquiring_dev;bool acq_dev_bg_active,in_isr;} spi_bus_lock_t;
struct spi_bus_lock_dev {spi_bus_lock_t* parent;unsigned mask;};
static unsigned enables,resumes;
static uint32_t lock_status_fetch(spi_bus_lock_t*l){return l->status;}
static uint32_t lock_status_fetch_set(spi_bus_lock_t*l,unsigned v){unsigned old=l->status;l->status|=v;return old;}
static uint32_t lock_status_fetch_clear(spi_bus_lock_t*l,unsigned v){unsigned old=l->status;l->status&=~v;return old;}
static void bg_enable(spi_bus_lock_t*l){(void)l;++enables;}
static void resume_dev_in_isr(spi_bus_lock_dev_t*d,BaseType_t*y){(void)d;(void)y;++resumes;}
'''
        code+='\n'.join(function(text,n) for n in ('update_pend_core','bg_exit_core','spi_bus_lock_bg_check_dev_req'))
        code+=r'''
int main(void){
 for(unsigned status=0;status<4;++status){
  spi_bus_lock_t l={.status=status,.in_isr=true};spi_bus_lock_dev_t d={&l,3};
  bool got=spi_bus_lock_bg_check_dev_req(&d);
  assert(got==(status!=0));assert(l.status==((status&1)?2:status));
  for(unsigned wip=0;wip<2;++wip){
   l.status=status;l.in_isr=true;enables=resumes=0;int yield=0;
   bool exit=bg_exit_core(&l,wip,&yield);
   assert(exit==(wip || !status));assert(enables==wip);assert(!resumes);
   assert(l.in_isr==(wip || status!=0));
  }
 }
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'probe.c').write_text(code)
            subprocess.run(['cc','-std=c11','-Wall','-Werror','-fsanitize=undefined',str(p/'probe.c'),'-o',str(p/'probe')],check=True,capture_output=True)
            subprocess.run([str(p/'probe')],check=True,capture_output=True)

if __name__=='__main__':unittest.main()

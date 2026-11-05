"""Pinned allocator normal nonshared source path; no hardware timing claim."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_s3_spi_lock_primitives import function

ROOT=Path(__file__).resolve().parents[1]


class RoutingTest(unittest.TestCase):
    def test_actual_external_source_enable_disable(self):
        source=(ROOT/'reports/s3-raw-tasks/sources/intr_alloc.c').read_text()
        shim=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#define ESP_INTR_IRAM_ATTR
#define ESP_OK 0
#define ESP_ERR_INVALID_ARG -1
#define INT_MUX_DISABLED_INTNO 6
typedef int esp_err_t;
typedef struct shared {int disabled,source;struct shared*next;} shared_vector_desc_t;
typedef struct {int source,cpu,intno;shared_vector_desc_t*shared_vec_info;} vector;
typedef struct {shared_vector_desc_t*shared_vector_desc;vector*vector_desc;} handle;
typedef handle* intr_handle_t;
static int spinlock,held,entries,exits,calls,route_cpu,route_source,route_int;
static void enter(int*l){assert(l==&spinlock&&!held);held=1;++entries;}
static void leave(int*l){assert(l==&spinlock&&held);held=0;++exits;}
#define portENTER_CRITICAL_SAFE(x) enter(x)
#define portEXIT_CRITICAL_SAFE(x) leave(x)
static void esp_rom_route_intr_matrix(int cpu,int source,int n){assert(held);++calls;route_cpu=cpu;route_source=source;route_int=n;}
static int esp_cpu_get_core_id(void){return 0;}
#define ESP_INTR_ENABLE(x) abort()
#define ESP_INTR_DISABLE(x) abort()
'''
        main=r'''
int main(void){
 for(int cpu=0;cpu<2;++cpu){
  vector v={.source=42,.cpu=cpu,.intno=19};handle h={.vector_desc=&v};
  entries=exits=calls=0;
  assert(esp_intr_enable(&h)==ESP_OK);
  assert(entries==1&&exits==1&&calls==1&&!held);
  assert(route_cpu==cpu&&route_source==42&&route_int==19);
  assert(esp_intr_disable(&h)==ESP_OK);
  assert(entries==2&&exits==2&&calls==2&&!held);
  assert(route_cpu==cpu&&route_source==42&&route_int==INT_MUX_DISABLED_INTNO);
 }
 return 0;
}
'''
        code=shim+'\n'.join(function(source,n) for n in ('esp_intr_enable','esp_intr_disable'))+main
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'route.c').write_text(code)
            r=subprocess.run(['cc','-std=c11','-Wall','-Werror','-fsanitize=undefined',str(p/'route.c'),'-o',str(p/'route')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            subprocess.run([str(p/'route')],check=True)

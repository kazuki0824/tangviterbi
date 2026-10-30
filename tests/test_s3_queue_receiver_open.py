import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class QueueReceiverOpen(unittest.TestCase):
 def test_pins_preserved_irq_contract_and_error_forwarding(self):
  with tempfile.TemporaryDirectory() as td:
   td=Path(td);(td/'driver').mkdir()
   s=(ROOT/'tests/s3_sdk_shim/driver/spi_master.h').read_text().replace('unsigned max_transfer_sz,flags;','unsigned max_transfer_sz,flags;int isr_cpu_id,intr_flags;int test_pin;')
   (td/'driver/spi_master.h').write_text(s)
   (td/'esp_intr_alloc.h').write_text('enum {ESP_INTR_CPU_AFFINITY_0=1,ESP_INTR_FLAG_IRAM=1024,ESP_INTR_FLAG_LEVEL1=2};\n')
   (td/'host.c').write_text('''
#include "s3_queue_receiver_open.h"
#include "esp_intr_alloc.h"
#include <assert.h>
static int calls;
esp_err_t s3_raw_queue_open(s3_raw_queue*q,s3_parallel_pack*p,spi_host_device_t h,const spi_bus_config_t*b,int cs,unsigned lanes,unsigned epoch){
 assert(!q&&!p&&h==SPI2_HOST&&cs==17&&lanes==8&&epoch==2);
 assert(b->test_pin==23&&b->max_transfer_sz==77&&b->flags==99);
 assert(b->isr_cpu_id==ESP_INTR_CPU_AFFINITY_0);
 assert(b->intr_flags==(ESP_INTR_FLAG_IRAM|ESP_INTR_FLAG_LEVEL1));++calls;return ESP_ERR_INVALID_STATE;
}
int main(void){spi_bus_config_t pins={.test_pin=23,.max_transfer_sz=77,.flags=99,.isr_cpu_id=2,.intr_flags=0x7fff};
 assert(s3_queue_receiver_open(0,0,SPI2_HOST,0,17,8,2)==ESP_ERR_INVALID_ARG&&calls==0);
 assert(s3_queue_receiver_open(0,0,SPI2_HOST,&pins,17,8,2)==ESP_ERR_INVALID_STATE&&calls==1);
 assert(pins.isr_cpu_id==2&&pins.intr_flags==0x7fff&&pins.test_pin==23);return 0;}
''')
   exe=td/'test';subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',f'-I{td}',f'-I{ROOT/"experiments"}',f'-I{ROOT/"tests/s3_sdk_shim"}',str(ROOT/'experiments/s3_queue_receiver_open.c'),str(td/'host.c'),'-o',str(exe)],check=True)
   subprocess.run([str(exe)],check=True)
if __name__=='__main__':unittest.main()

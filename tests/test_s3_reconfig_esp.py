"""Actual SDK GPIO adapter; no pulse allowed while any owner remains active."""
from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class ReconfigTest(unittest.TestCase):
 def test_release_before_output_and_quiescent_pulse(self):
  out=ROOT/'build/s3-reconfig-esp';(out/'driver').mkdir(parents=True,exist_ok=True)
  (out/'driver/gpio.h').write_text('''#include <stdint.h>
enum {ESP_OK=0,GPIO_MODE_OUTPUT_OD=3,GPIO_PULLUP_DISABLE=0,GPIO_PULLDOWN_DISABLE=0,GPIO_INTR_DISABLE=0};
typedef struct {uint64_t pin_bit_mask;unsigned mode,pull_up_en,pull_down_en,intr_type;}gpio_config_t;
int gpio_set_level(unsigned,unsigned);int gpio_config(const gpio_config_t*);
''')
  (out/'esp_rom_sys.h').write_text('void esp_rom_delay_us(unsigned);\n')
  (out/'test.c').write_text(r'''
#include "s3_reconfig_esp.h"
#include "driver/gpio.h"
#include <assert.h>
#include <stdio.h>
static bool idle;static unsigned calls,levels[4];
static bool quiescent(void*p){(void)p;return idle;}
int gpio_set_level(unsigned pin,unsigned level){assert(pin==40);levels[calls++]=level;return 0;}
int gpio_config(const gpio_config_t*c){assert(calls==1&&levels[0]==1);assert(c->pin_bit_mask==(UINT64_C(1)<<40)&&c->mode==GPIO_MODE_OUTPUT_OD&&!c->pull_up_en&&!c->pull_down_en);return 0;}
void esp_rom_delay_us(unsigned n){assert(calls==2&&levels[1]==0&&n==5);}
int main(void){s3_reconfig_esp s={0};assert(!s3_reconfig_esp_open(&s,quiescent,0)&&!calls);
 idle=true;assert(s3_reconfig_esp_open(&s,quiescent,0));idle=false;assert(!s3_reconfig_esp_pulse(&s)&&calls==1);
 idle=true;assert(s3_reconfig_esp_pulse(&s)&&calls==3&&levels[2]==1);
 puts("PASS preload release, open-drain GPIO40, refuse pulse before quiescence, 5us low and release");}
''')
  subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-DESP_PLATFORM','-I'+str(out),'-Iexperiments','experiments/s3_reconfig_esp.c',str(out/'test.c'),'-o',str(out/'sim')],cwd=ROOT,check=True)
  r=subprocess.run([str(out/'sim')],capture_output=True,text=True,timeout=15);(out/'simulation.log').write_text(r.stdout+r.stderr);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()

"""Build-only namespace/IRAM adapter of the hash-pinned ESP-DSP assembly."""
import hashlib,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def coefficients():
 values=[]
 for j in range(4096):
  k=int(f'{j:012b}'[::-1],2);angle=2*math.pi*k/8192
  values.extend((int(32767*math.cos(angle)),int(32767*math.sin(angle))))
 return ('/* Fixed ESP-DSP sc16 coefficients: 32767 scale, positive sine, bit-reversed pairs. */\n'
  'const int16_t s3_fft_simd_table[8192] __attribute__((aligned(16))) = {\n'+
  '\n'.join('    '+', '.join(map(str,values[i:i+16]))+',' for i in range(0,len(values),16))+'\n};\n')
def source():
 p=ROOT/'experiments/s3_fft_simd_port'
 manifest=json.loads((p/'upstream.json').read_text())
 for name,sha in manifest['sha256'].items():
  if hashlib.sha256((p/name).read_bytes()).hexdigest()!=sha:raise ValueError('modified upstream: '+name)
 text=(p/'dsps_fft2r_sc16_aes3.S').read_text()
 text=text.replace('#include "dsps_fft2r_platform.h"','#define dsps_fft2r_sc16_aes3_enabled 1')
 text=text.replace('dsps_fft2r_sc16_aes3_','s3_pinned_fft_aes3')
 text=text.replace('dsps_fft2r_sc16_initialized','s3_pinned_fft_initialized')
 text=text.replace('dsp_is_power_of_two','s3_pinned_fft_power_of_two')
 text=text.replace('\t.text','\t.section .iram1,"ax"')
 return '/* Derived from ESP-DSP '+manifest['commit']+'; namespace/header/IRAM changes only. */\n'+text

def host_source():
 """Pristine upstream ANSI arithmetic for order/table tests, NOT SIMD emulation."""
 p=ROOT/'experiments/s3_fft_simd_port/dsps_fft2r_sc16_ansi.c'
 text=p.read_text()
 helpers=text[text.index('static const int add_rount_mult'):text.index('esp_err_t dsps_fft2r_init_sc16')]
 body=text[text.index('esp_err_t dsps_fft2r_sc16_ansi_'):text.index('static inline unsigned short reverse_sc16')]
 body=body.replace('dsps_fft2r_sc16_ansi_','s3_pinned_fft_aes3')
 body=body.replace('dsps_fft2r_sc16_initialized','s3_pinned_fft_initialized').replace('dsp_is_power_of_two','s3_pinned_fft_power_of_two')
 return '''/* Host-only ANSI oracle; never executes/emulates S3 SIMD instructions. */
#include <stdint.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_DSP_INVALID_LENGTH 1
#define ESP_ERR_DSP_UNINITIALIZED 2
typedef union { struct { int16_t re,im; }; uint32_t data; } sc16_t;
extern uint8_t s3_pinned_fft_initialized;
extern int s3_pinned_fft_power_of_two(int n);
'''+helpers+body
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(source())

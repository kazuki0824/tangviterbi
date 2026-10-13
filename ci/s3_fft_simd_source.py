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

def tiled_source():
 """Extract the three pinned vector butterfly loops, with short-call setup."""
 source() # Verify pristine upstream hashes before deriving any loop.
 text=(ROOT/'experiments/s3_fft_simd_port/dsps_fft2r_sc16_aes3.S').read_text()
 license=text[:text.index('#include')]
 loops=[]
 for first,last in ((52,54),(74,76),(96,98)):
  block=text.split(f'.LBB{first}_dsps_fft2r_sc16_aes3_:',1)[1].split(f'.LBB{last}_dsps_fft2r_sc16_aes3_:',1)[0]
  block=block.split('\n',1)[1]
  loops.append(block)
 general=loops[0].replace('a8','a3').replace('a9','a2')
 pair=loops[1].replace('a8','a2').replace('a9','a3')
 final=loops[2].replace('a4','a3')
 result=license+'/* Derived vector loops; new ABI/setup/loop count, same pinned arithmetic. */\n.section .iram1,"ax"\n.literal_position\n.literal .Ls3_tile_scale,32767\n'
 for name,body,count in (('s3_fft_simd_general',general,'a5'),('s3_fft_simd_pair',pair,'a4'),('s3_fft_simd_final',final,'a4')):
  result+=f'''.align 4
.global {name}
.type {name},@function
{name}:
 entry a1,64
 movi a8,16
 wsr.sar a8
 l32r a7,.Ls3_tile_scale
 s16i a7,a1,0
 mov.n a6,a1
 ee.vldbc.16.ip q6,a6,0
'''
  if name=='s3_fft_simd_general':result+=' ee.vldbc.32.ip q5,a4,0\n'
  result+=f' loopnez {count},.L{name}_end\n'+body+f'.L{name}_end:\n retw.n\n'
 return result

def host_tiled_source():
 text=host_source();text=text[:text.index('esp_err_t s3_pinned_fft_aes3')]
 return text+'''
static void bf(sc16_t *a,sc16_t *b,sc16_t w) {
 sc16_t x=*a,y=*b,lo,hi;
 lo.re=xtfixed_bf_1(x.re,w.re,y.re,w.im,y.im,16);
 lo.im=xtfixed_bf_2(x.im,w.re,y.im,w.im,y.re,16);
 hi.re=xtfixed_bf_3(x.re,w.re,y.re,w.im,y.im,16);
 hi.im=xtfixed_bf_4(x.im,w.re,y.im,w.im,y.re,16);
 *a=hi;*b=lo;
}
void s3_fft_simd_general(int16_t *a,int16_t *b,const int16_t *w,unsigned blocks) {
 sc16_t c=*(const sc16_t *)w;
 for(unsigned i=0;i<4*blocks;++i)bf((sc16_t *)a+i,(sc16_t *)b+i,c);
}
void s3_fft_simd_pair(int16_t *data,const int16_t *table,unsigned blocks) {
 sc16_t *d=(sc16_t *)data;const sc16_t *w=(const sc16_t *)table;
 for(unsigned i=0;i<2*blocks;++i)for(unsigned k=0;k<2;++k)bf(d+4*i+k,d+4*i+k+2,w[i]);
}
void s3_fft_simd_final(int16_t *data,const int16_t *table,unsigned blocks) {
 sc16_t *d=(sc16_t *)data;const sc16_t *w=(const sc16_t *)table;
 for(unsigned i=0;i<4*blocks;++i)bf(d+2*i,d+2*i+1,w[i]);
}
'''
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(source())

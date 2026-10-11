#!/usr/bin/env python3
"""Compile pinned S3 SIMD FFT; does not execute it or establish silicon WCET."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
from s3_fft_simd_source import source,tiled_source
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',default='xtensa-esp32s3-elf-gcc');a=p.parse_args()
 cc=shutil.which(a.cc) or a.cc;prefix=cc[:-3]
 b=ROOT/'build/s3-fft-simd';b.mkdir(parents=True,exist_ok=True)
 out=ROOT/'reports/s3-fft-simd-evidence';out.mkdir(parents=True,exist_ok=True)
 (b/'kernel.S').write_text(source())
 (b/'tiles.S').write_text(tiled_source())
 flags=['-O3','-std=c11','-Wall','-Wextra','-Werror','-mlongcalls','-fstack-usage']
 for name,path in [('kernel',b/'kernel.S'),('wrapper',ROOT/'experiments/s3_fft_simd.c'),('scalar',ROOT/'experiments/s3_fft_tiles.c'),
                  ('tiles',b/'tiles.S'),('tiles-c',ROOT/'experiments/s3_fft_simd_tiles.c')]:
  subprocess.run([cc,*flags,'-c',str(path),'-o',str(b/(name+'.o'))],check=True)
 subprocess.run([cc,'-r',*[str(b/(n+'.o')) for n in ('kernel','wrapper','scalar','tiles','tiles-c')],'-o',str(b/'bundle.o')],check=True)
 undefined=subprocess.check_output([prefix+'nm','-u',str(b/'bundle.o')],text=True).strip()
 if undefined:raise ValueError('unresolved FFT bundle symbols: '+undefined)
 sizes=subprocess.check_output([prefix+'size','-A',str(b/'bundle.o')],text=True)
 asm=subprocess.check_output([prefix+'objdump','-dr',str(b/'bundle.o')],text=True)
 (out/'bundle.disasm').write_text('\n'.join(x.rstrip() for x in asm.splitlines())+'\n')
 (out/'sizes.txt').write_text(sizes)
 if 'ee.cmul.s16' not in asm or 's3_pinned_fft_aes3' not in asm:raise ValueError('missing S3 SIMD kernel')
 result=dict(scope=__doc__,compiler=subprocess.check_output([cc,'--version'],text=True).splitlines()[0],
  upstream=json.loads((ROOT/'experiments/s3_fft_simd_port/upstream.json').read_text()),
  source_sha256={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in
   [ROOT/'experiments'/n for n in ('s3_fft_simd.c','s3_fft_simd.h','s3_fft_simd_coefficients.inc','s3_fft_simd_tiles.c','s3_fft_simd_tiles.h')]+[
    ROOT/'ci/s3_fft_simd_source.py',ROOT/'ci/s3_fft_simd_evidence.py']},
  bundle_sha256=hashlib.sha256((b/'bundle.o').read_bytes()).hexdigest(),
  coefficient_bytes=16384,frame_bytes=32768,frames=2,
  internal_coefficient_growth_vs_quarter_bytes=16384-4098,
  SDK_ELF_link_verified=False,CPU_WCET_verified=False,SIMD_executed=False,
  SIMD_ANSI_bit_equivalence_verified=False,receiver_adopted=False,
  deployment_contract='FFT core1 with local interrupt mask; RF core0 never waits on the FFT lock. Frame and copied coefficients must be internal SRAM. High-priority/NMI code cannot use PIE.',
  unknown=['8192-point simultaneous RF/DMA WCET','whole-system IRQ/vector context verification',
           'all runtime internal allocations','end-to-end demodulation quality'])
 host=b/'host-oracle.json'
 if host.exists():result['host_ANSI_oracle']=json.loads(host.read_text());shutil.copy2(host,out/host.name)
 host=b/'tile-host-oracle.json'
 if host.exists():result['tile_ANSI_oracle']=json.loads(host.read_text());shutil.copy2(host,out/host.name)
 for name in ('kernel.S','tiles.S','unittest.txt','tile-unittest.txt'):
  if (b/name).exists():shutil.copy2(b/name,out/name)
 (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 print(sizes);print(json.dumps({k:result[k] for k in ('coefficient_bytes','internal_coefficient_growth_vs_quarter_bytes','CPU_WCET_verified')},indent=2))
if __name__=='__main__':main()

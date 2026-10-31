"""Validate the SDK artifact source identity and common-clock hot-code placement."""
import argparse,gzip,hashlib,io,json,subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--commit',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 d=json.loads((a.profile/'result.json').read_text());data=gzip.decompress((a.profile/'s3_raw_probe.elf.gz').read_bytes());e=ELFFile(io.BytesIO(data));symbols={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()};checks=[]
 checks.append(dict(name='ELF_hash',passed=hashlib.sha256(data).hexdigest()==d['ELF_sha256']))
 for name in ['experiments/s3_timer_clock.c','experiments/s3_timer_clock.h','experiments/s3_native_capture.c','experiments/s3_native_capture.h','experiments/s3_parallel_pack.c','experiments/s3_parallel_pack.h','experiments/s3_parallel_capture.c','experiments/s3_raw_probe/main/raw_probe.c']:
  expected=hashlib.sha256(subprocess.check_output(['git','show',a.commit+':'+name],cwd=ROOT)).hexdigest()
  checks.append(dict(name='source_'+name,passed=d['build']['source_sha256'].get(name)==expected))
 hot={}
 for name in ['s3_timer_clock','s3_pp_step_timer','s3_pp_step_clocked_quantized','s3_native_poll','esp_timer_get_time','systimer_hal_get_counter_value']:
  s=symbols.get(name);section=e.get_section(s['st_shndx']).name if s is not None else ''
  ok=s is not None and section.startswith('.iram')
  checks.append(dict(name='IRAM_'+name,passed=ok))
  if s is not None:hot[name]=dict(address=hex(s['st_value']),bytes=s['st_size'],section=section)
 report=dict(commit=a.commit,ELF_sha256=d['ELF_sha256'],checks=checks,SDK_static_check_count=len(d['checks']),SDK_all_static_checks_pass=d['all_static_checks_pass'],sizes=d['sizes'],symbols=d['symbols'],hot=hot,hardware_boot_executed=False,clock_WCET_bound_proven=False)
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2));return any(not x['passed'] for x in checks) or not d['all_static_checks_pass']
if __name__=='__main__':raise SystemExit(main())

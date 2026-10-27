"""Compare SDK fill machine instructions to audited object; exclude only literal relocation."""
import argparse,gzip,hashlib,io,json,os,re,subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
from ci.s3_pack_cfg_audit import ROW
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--commit',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 r=json.loads((a.profile/'result.json').read_text());data=gzip.decompress((a.profile/'s3_raw_probe.elf.gz').read_bytes());e=ELFFile(io.BytesIO(data));symbols={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()};s=next(v for k,v in symbols.items() if k.startswith('fill$'));lo=s['st_value'];hi=lo+s['st_size']
 elf=ROOT/'build/fill-sdk-audit.elf';elf.write_bytes(data);tc=a.toolchain.resolve();env=os.environ.copy();env['XTENSA_GNU_CONFIG']=str(tc/'lib/xtensa_esp32s3.so')
 dis=subprocess.check_output([str(tc/'bin/xtensa-esp-elf-objdump'),'-d',f'--start-address={lo}',f'--stop-address={hi}',str(elf)],env=env,text=True)
 def rows(text):return [m for line in text.splitlines() if (m:=ROW.match(line)) and m[3]!='ill']
 target=rows((ROOT/'reports/s3-fill-unroll/u8/fill.dis').read_text());actual=rows(dis)
 def normalized(rs):return [(int(m[1],16)-int(rs[0][1],16),m[3],m[2] if m[3]!='l32r' else 'literal relocation') for m in rs]
 checks=[dict(name='ELF_hash',passed=hashlib.sha256(data).hexdigest()==r['ELF_sha256']),dict(name='all_SDK_static_checks',passed=r['all_static_checks_pass']),dict(name='same_machine_instructions_except_literal_relocation',passed=normalized(target)==normalized(actual))]
 literals=[int(re.search(r', ([0-9a-f]+) <',m[4])[1],16) for m in actual if m[3]=='l32r']
 def word(addr):
  section=next(sec for sec in e.iter_sections() if sec['sh_addr']<=addr<sec['sh_addr']+sec['sh_size']);offset=addr-section['sh_addr'];return int.from_bytes(section.data()[offset:offset+4],'little')
 checks.append(dict(name='sentinel_literal',passed=len(literals)==1 and word(literals[0])==0xa5c33c5a))
 for path in ('experiments/s3_native_capture.c','experiments/s3_parallel_pack.c','experiments/s3_spi_transport.c','experiments/s3_raw_probe/main/CMakeLists.txt','experiments/s3_raw_probe/main/raw_probe.c'):
  digest=hashlib.sha256(subprocess.check_output(['git','show',a.commit+':'+path],cwd=ROOT)).hexdigest();checks.append(dict(name='source_'+path,passed=digest==r['build']['source_sha256'][path]))
 result=dict(commit=a.commit,checks=checks,fill_bytes=s['st_size'],static_instructions=len(actual),fill_instruction_envelope_per_bank=15362 if all(c['passed'] for c in checks) else None,ELF_sha256=r['ELF_sha256'],symbols=r['symbols'],sizes=r['sizes'],driver_lower_bound=r['driver_lower_bound'],SDK_static_checks=len(r['checks']),hardware_boot_executed=False,WCET_measured=False)
 (a.output/'sdk-fill.dis').write_text(dis);(a.output/'sdk-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return any(not c['passed'] for c in checks)
if __name__=='__main__':raise SystemExit(main())

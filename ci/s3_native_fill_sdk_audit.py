"""Recheck optimized fill and unchanged packing against the downloaded SDK ELFs."""
import argparse,gzip,hashlib,io,json,os,re,subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
from ci.s3_pack_cfg_audit import ROW
ROOT=Path(__file__).resolve().parents[1]
def image(profile):
 data=gzip.decompress((profile/'s3_raw_probe.elf.gz').read_bytes());e=ELFFile(io.BytesIO(data));symbols={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()}
 def code(name):
  s=symbols[name];section=e.get_section(s['st_shndx']);offset=s['st_value']-section['sh_addr'];return section.data()[offset:offset+s['st_size']]
 return data,symbols,code

def main():
 p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);a=p.parse_args()
 out=ROOT/'reports/s3-pack-span/native-fill-optimized';name='n16r8-late-stacks-no-phy-nvs-raw-only-spi';profile=out/'sdk'/name
 data,symbols,code=image(profile);old,oldsymbols,oldcode=image(ROOT/'reports/s3-pack-span/sdk'/name)
 result=json.loads((profile/'result.json').read_text());checks=[]
 checks.append(dict(name='ELF_hash_matches_CI',ok=hashlib.sha256(data).hexdigest()==result['ELF_sha256']))
 for path in ['experiments/s3_native_capture.c','experiments/s3_parallel_pack.c']:
  checks.append(dict(name='CI_source_'+path,ok=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==result['build']['source_sha256'][path]))
 for name in ['pack_eight','s3_pp_step_impl','s3_pp_step_clocked']:
  checks.append(dict(name='same_packing_bytes_and_address_'+name,ok=code(name)==oldcode(name) and symbols[name]['st_value']==oldsymbols[name]['st_value']))
 s=next(v for k,v in symbols.items() if k.startswith('fill$'));lo=s['st_value'];hi=lo+s['st_size'];elf=ROOT/'build/native-fill-target/new-sdk.elf';elf.write_bytes(data)
 tc=a.toolchain.resolve();env=os.environ.copy();env['XTENSA_GNU_CONFIG']=str(tc/'lib/xtensa_esp32s3.so')
 dis=subprocess.check_output([str(tc/'bin/xtensa-esp-elf-objdump'),'-d',f'--start-address={lo}',f'--stop-address={hi}',str(elf)],env=env,text=True)
 rows=[(int(m[1],16),m[3],m[4]) for line in dis.splitlines() if (m:=ROW.match(line))]
 loop=next(i for i,r in enumerate(rows) if r[1]=='loop');end=int(re.search(r', ([0-9a-f]+) <',rows[loop][2])[1],16);body=[r for r in rows[loop+1:] if r[0]<end]
 checks.append(dict(name='SDK_three_instruction_loop',ok=[r[1] for r in body]==['memw','s32i.n','addi.n']))
 checks.append(dict(name='SDK_fill_25_instruction_shape',ok=len(rows)==25))
 layouts=[]
 for q in (out/'sdk').iterdir():
  new=json.loads((q/'result.json').read_text());before=json.loads((ROOT/'reports/s3-pack-span/sdk'/q.name/'result.json').read_text())
  layouts.append(dict(profile=q.name,checks=len(new['checks']),passed=new['all_static_checks_pass'],symbols=new['symbols'],heap_start_delta=int(new['symbols']['_heap_start'],16)-int(before['symbols']['_heap_start'],16)))
 r=dict(commit='176653a216363191004efc17390e4aafebec7126',run_id=40192845126,artifact_id=12598732910,archive_sha256='2a00f43e2ffed941c28131683134c85d07da130301865a0894b8934073a7e278',ELF_sha256=result['ELF_sha256'],checks=checks,layouts=layouts,fill_symbol=hex(lo),fill_bytes=s['st_size'],fill_static_instructions=len(rows),body_ops=[r[1] for r in body],WCET_measured=False)
 (out/'sdk-verification.json').write_text(json.dumps(r,indent=2)+'\n');(out/'sdk-fill.dis').write_text(dis);print(json.dumps(r,indent=2));return any(not c['ok'] for c in checks)
if __name__=='__main__':raise SystemExit(main())

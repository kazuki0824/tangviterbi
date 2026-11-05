#!/usr/bin/env python3
"""Build pinned SDK sources and package a symbol-bearing, hash-bound image.

The complete debug ELF is retained as deterministic gzip chunks. The compact
provided ELF strips debug only; all allocated bytes/addresses and symbols are
verified against the full image. This tool does not flash or start a target.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
import shlex
import subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile

ROOT=Path(__file__).resolve().parents[2]
PROJECT=Path(__file__).resolve().parent
PIN='fcae32885b0296b32044cb99ecbdc50d98dddb83'
ARTIFACTS=('t_preprocess_integration_probe.elf.gz','t_preprocess_integration_probe.map.gz',
           'sdkconfig.gz','sdkconfig.json.gz','sdkconfig.h.gz','compile_commands.json.gz',
           'project_description.json.gz','build.log.gz','python-packages.txt','idf-submodules.txt','stack-usage.json')
def sha(data):return hashlib.sha256(data).hexdigest()
def run(args,**kw):return subprocess.run([str(x) for x in args],check=True,text=True,capture_output=True,**kw).stdout
def allocated(raw):
    elf=ELFFile(io.BytesIO(raw))
    return [dict(name=s.name,address=int(s['sh_addr']),size=int(s['sh_size']),flags=int(s['sh_flags']),
                 type=s['sh_type'],sha256=sha(s.data())) for s in elf.iter_sections() if int(s['sh_flags'])&2]
def sources(commands,build,env):
    found=set()
    for row in commands:
        if 'esp-idf/main/' not in row.get('output',row.get('command','')):continue
        found.add(Path(row['file']).resolve());obj=row.get('output')
        if not obj:
            args=shlex.split(row['command']);obj=args[args.index('-o')+1]
        for line in run(['ninja','-C',build,'-t','deps',obj],env=env).splitlines():
            if line.startswith('    '):
                p=Path(line.strip())
                if p.is_file():found.add(p.resolve())
    for p in PROJECT.rglob('*'):
        if p.is_file() and not {'build','__pycache__'}&set(p.relative_to(PROJECT).parts) and p.name not in ('sdkconfig','sdkconfig.old'):
            found.add(p.resolve())
    return {str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in sorted(found)
            if p.is_relative_to(ROOT) and not p.is_relative_to(build)}
def main():
    ap=argparse.ArgumentParser()
    for name in ('idf','toolchain','idf-tools','python-env'):ap.add_argument('--'+name,type=Path,required=True)
    ap.add_argument('--config',type=Path,default=ROOT/'reports/s3-t-preprocess-integration-v2/sdk/sdkconfig.gz',
                    help='Pinned full sdkconfig, raw or gzip; independent of output directory')
    ap.add_argument('--output',type=Path,default=ROOT/'reports/s3-t-preprocess-integration-v2/sdk')
    ap.add_argument('--no-build',action='store_true',help='Package an already successful local build')
    a=ap.parse_args()
    for name in ('idf','toolchain','idf_tools','python_env','output','config'):setattr(a,name,getattr(a,name).resolve())
    a.output.mkdir(parents=True,exist_ok=True)
    commit=run(['git','-C',a.idf,'rev-parse','HEAD']).strip()
    if commit!=PIN:raise ValueError('IDF commit is not pinned v5.5.1')
    submodules=run(['git','-C',a.idf,'submodule','status','--recursive'])
    if any(line[:1] in '+-U' for line in submodules.splitlines()):raise ValueError('IDF submodules are not pinned')
    env=dict(os.environ,IDF_TARGET='esp32s3',IDF_PATH=str(a.idf),IDF_TOOLS_PATH=str(a.idf_tools),
             IDF_PYTHON_ENV_PATH=str(a.python_env),ESP_ROM_ELF_DIR=str(a.idf_tools/'tools/esp-rom-elfs/20241011'),
             XTENSA_GNU_CONFIG=str(a.toolchain/'lib/xtensa_esp32s3.so'))
    env['PATH']=os.pathsep.join([str(a.python_env/'bin'),str(a.toolchain/'bin'),
        str(a.idf_tools/'tools/esp32ulp-elf/2.38_20240113/esp32ulp-elf/bin'),env['PATH']])
    compiler=run([a.toolchain/'bin/xtensa-esp-elf-gcc','--version'],env=env).strip()
    if 'esp-14.2.0_20241119' not in compiler:raise ValueError('compiler version mismatch')
    build=PROJECT/'build'
    if not a.no_build:
        data=a.config.read_bytes()
        if str(a.config).endswith('.gz'):data=gzip.decompress(data)
        (PROJECT/'sdkconfig').write_bytes(data)
        result=subprocess.run([str(a.python_env/'bin/python'),str(a.idf/'tools/idf.py'),'build'],cwd=PROJECT,
                               env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (a.output/'build.log.gz').write_bytes(gzip.compress(result.stdout.encode(),mtime=0))
        if result.returncode:print(result.stdout[-7000:]);return result.returncode
    full=build/'t_preprocess_integration_probe.elf';small=build/'t_preprocess_integration_probe.sym.elf'
    run([a.toolchain/'bin/xtensa-esp-elf-objcopy','--strip-debug',full,small],env=env)
    raw=full.read_bytes();sr=small.read_bytes();fa=allocated(raw)
    if fa!=allocated(sr):raise ValueError('Debug stripping changed allocated contents/address/layout')
    if not ELFFile(io.BytesIO(sr)).get_section_by_name('.symtab'):raise ValueError('Stripped ELF lost symbols')
    sgz=gzip.compress(sr,mtime=0);(a.output/'t_preprocess_integration_probe.elf.gz').write_bytes(sgz)
    fgz=gzip.compress(raw,mtime=0);parts=a.output/'full-elf.parts';parts.mkdir(exist_ok=True);chunks=[]
    for i,start in enumerate(range(0,len(fgz),240000)):
        p=parts/f'part-{i:03d}';data=fgz[start:start+240000];p.write_bytes(data)
        chunks.append(dict(path=str(p.relative_to(a.output)),bytes=len(data),sha256=sha(data)))
    keep={Path(r['path']).name for r in chunks}
    for stale in parts.glob('part-*'):
        if stale.is_file() and stale.name not in keep:stale.unlink()
    for src,dst in [(PROJECT/'sdkconfig','sdkconfig.gz'),(build/'config/sdkconfig.json','sdkconfig.json.gz'),
        (build/'compile_commands.json','compile_commands.json.gz'),(build/'project_description.json','project_description.json.gz'),
        (build/'t_preprocess_integration_probe.map','t_preprocess_integration_probe.map.gz'),(build/'config/sdkconfig.h','sdkconfig.h.gz')]:
        (a.output/dst).write_bytes(gzip.compress(src.read_bytes(),mtime=0))
    commands=json.loads((build/'compile_commands.json').read_text())
    (a.output/'python-packages.txt').write_text(run([a.python_env/'bin/python','-m','pip','freeze'],env=env))
    (a.output/'idf-submodules.txt').write_text(submodules)
    stack_rows={str(p.relative_to(build)):p.read_text() for p in (build/'esp-idf/main').rglob('*.su')}
    (a.output/'stack-usage.json').write_text(json.dumps(stack_rows,indent=2)+'\n')
    d=dict(schema_version=2,kind='fresh linked reconstruction; not a recovered prior ELF',idf_commit=commit,
        compiler=compiler,source_sha256=sources(commands,build,env),config_sha256=sha((PROJECT/'sdkconfig').read_bytes()),
        full_elf_sha256=sha(raw),full_elf_bytes=len(raw),provided_elf_sha256=sha(sr),provided_elf_bytes=len(sr),
        provided_elf_gzip_bytes=len(sgz),full_elf_gzip_sha256=sha(fgz),full_elf_gzip_bytes=len(fgz),full_elf_chunks=chunks,
        allocated_sections_identical=True,allocated_sections=fa,
        source_head_at_packaging=run(['git','-C',ROOT,'rev-parse','HEAD']).strip(),
        configured_project_version=json.loads((build/'project_description.json').read_text()).get('project_version'),
        target_executed=False,flashed=False,tool_archives={
            'xtensa':dict(version='esp-14.2.0_20241119',sha256='e3e6dcf3d275c3c9ab0e4c8a9d93fd10e7efc035d435460576c9d95b4140c676'),
            'rom':dict(version='20241011',sha256='921f000164a421c7628fbfee55b173384aafaa51883adc65cd27bf9b0af9e9a9')},
        build_command='python experiments/t_preprocess_integration_probe/build_probe.py --idf IDF --toolchain XTENSA_ROOT --idf-tools IDF_TOOLS --python-env VENV --config PINNED_CONFIG --output OUTPUT',
        artifact_sha256={name:sha((a.output/name).read_bytes()) for name in ARTIFACTS})
    (a.output/'provenance.json').write_text(json.dumps(d,indent=2)+'\n')
    print(json.dumps({k:d[k] for k in ('full_elf_bytes','provided_elf_bytes','provided_elf_gzip_bytes','full_elf_gzip_bytes','provided_elf_sha256')},indent=2))
    return 0
if __name__=='__main__':raise SystemExit(main())

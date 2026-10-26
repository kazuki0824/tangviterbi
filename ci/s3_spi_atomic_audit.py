"""Pinned executable atomic dispatch/retry audit; not a cycle bound."""
import argparse,gzip,hashlib,io,json,os
from pathlib import Path
from elftools.elf.elffile import ELFFile
from ci.s3_pack_cfg_audit import graph
ROOT=Path(__file__).resolve().parents[1]

def audit(toolchain,output):
    profile=ROOT/'reports/s3-raw-tasks/sdk-launcher/n16r8-late-stacks-no-phy-nvs-raw-only-spi'
    data=gzip.decompress((profile/'s3_raw_probe.elf.gz').read_bytes())
    expected=json.loads((profile/'result.json').read_text())['ELF_sha256']
    assert hashlib.sha256(data).hexdigest()==expected
    output.mkdir(parents=True,exist_ok=True);tmp=ROOT/'build/atomic-probe.elf';tmp.parent.mkdir(exist_ok=True);tmp.write_bytes(data)
    e=ELFFile(io.BytesIO(data));syms={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()}
    env=dict(os.environ,XTENSA_GNU_CONFIG=str(toolchain/'lib/xtensa_esp32s3.so'))
    names=['spi_bus_lock_bg_request','spi_bus_lock_bg_check_dev_req','__atomic_fetch_or_4','__atomic_fetch_and_4','__atomic_s32c1i_fetch_or_4','__atomic_s32c1i_fetch_and_4']
    gs={n:graph(tmp,str(toolchain/'bin/xtensa-esp-elf-objdump'),env,syms[n]['st_value'],syms[n]['st_size']) for n in names}
    checks=[]
    def check(n,v):
        checks.append(dict(name=n,passed=bool(v)))
        if not v:raise AssertionError(n)
    check('pinned ELF',expected=='7ee25471a6dc96c056c2afd883cf4f70282fd186be920cced7dddefa40554fc7')
    for suffix,loop,cas,branch in [('or',0x40385c9e,0x40385ca6,0x40385cab),('and',0x40385c82,0x40385c8a,0x40385c8f)]:
        wrapper=gs['__atomic_fetch_'+suffix+'_4'];g=gs['__atomic_s32c1i_fetch_'+suffix+'_4']
        check(suffix+' dispatch address constants',any('(c4000000 ' in x['operands'] for x in wrapper.values()) and any('(1ffffff ' in x['operands'] for x in wrapper.values()))
        check(suffix+' dispatch unsigned comparison',sum(x['op']=='bgeu' for x in wrapper.values())==1)
        check(suffix+' helper target',any('<__atomic_s32c1i_fetch_'+suffix+'_4>' in x['operands'] for x in wrapper.values()))
        check(suffix+' one CAS',g[cas]['op']=='s32c1i' and sum(x['op']=='s32c1i' for x in g.values())==1)
        check(suffix+' retry edge',g[branch]['op']=='bne' and hex(loop) in g[branch]['edges'])
        check(suffix+' IRAM',e.get_section(syms['__atomic_s32c1i_fetch_'+suffix+'_4']['st_shndx']).name=='.iram0.text')
    check('request calls OR',any('<__atomic_fetch_or_4>' in x['operands'] for x in gs[names[0]].values()))
    check('check request calls OR and AND',all(any('<__atomic_fetch_'+op+'_4>' in x['operands'] for x in gs[names[1]].values()) for op in ('or','and')))
    lock=(ROOT/'reports/s3-spi-wait-audit/sources/spi_bus_lock.c').read_text()
    check('bus lock internal allocation','heap_caps_calloc(1, sizeof(spi_bus_lock_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)' in lock)
    (output/'reachable.json').write_text(json.dumps({n:list(g.values()) for n,g in gs.items()},indent=2)+'\n')
    (output/'reachable.txt').write_text('\n\n'.join(n+'\n'+'\n'.join(f"{pc:08x}: {x['op']} {x['operands']}" for pc,x in sorted(g.items())) for n,g in gs.items())+'\n')
    result=dict(ELF_sha256=expected,checks=checks,internal_path='S32C1I retry, not fallback global spinlock',
                conditional_ISR_total_extra_CAS_retries=1,owner_CAS_retry_upper=None,
                cycles_upper=None,WCET_proven=False,receiver_adopted=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=audit(a.toolchain.resolve(),a.output);print(len(r['checks']),'checks passed')

"""Inspect actual SDK watchdog wait path; no instruction-to-cycle conversion."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
from elftools.elf.elffile import ELFFile
from ci.s3_pack_cfg_audit import graph
ROOT = Path(__file__).resolve().parents[1]


def audit(profile, toolchain, output):
    raw = gzip.decompress((profile/'s3_raw_probe.elf.gz').read_bytes())
    d = json.loads((profile/'result.json').read_text())
    e = ELFFile(io.BytesIO(raw))
    syms = {s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()}
    output.mkdir(parents=True,exist_ok=True)
    tmp = ROOT/'build/task-wait-audit.elf';tmp.write_bytes(raw)
    env = dict(os.environ,XTENSA_GNU_CONFIG=str(toolchain/'lib/xtensa_esp32s3.so'))
    names = ('esp_task_wdt_reset','xPortEnterCriticalTimeout','feed')
    graphs = {n:graph(tmp,str(toolchain/'bin/xtensa-esp-elf-objdump'),env,
                      syms[n]['st_value'],syms[n]['st_size']) for n in names}
    checks = []
    def check(name, value):
        checks.append(dict(name=name,passed=bool(value)))
    check('ELF_hash',hashlib.sha256(raw).hexdigest()==d['ELF_sha256'])
    check('SDK_static_checks',d['all_static_checks_pass'])
    # Audited addresses are deliberately pinned: relocation/optimization needs
    # a fresh review, not a successful match on an unrelated textual mnemonic.
    reset = graphs['esp_task_wdt_reset'];lock = graphs['xPortEnterCriticalTimeout']
    check('reset_wait_forever_argument', reset[0x4200d7c5]['op']=='movi.n' and
          reset[0x4200d7c5]['operands']=='a11, -1')
    check('reset_critical_target', reset[0x4200d7c7]['op']=='l32r' and
          '<xPortEnterCriticalTimeout>' in reset[0x4200d7c7]['operands'] and
          reset[0x4200d7ca]['op']=='callx8')
    check('forever_branch',lock[0x4037f5cb]['op']=='beqi' and
          lock[0x4037f5cb]['operands'].startswith('a3, -1,') and
          '0x4037f5e8' in lock[0x4037f5cb]['edges'])
    loop=[];pc=0x4037f5e8
    while pc not in loop:
        loop.append(pc);node=lock[pc]
        if pc==0x4037f5f4:break
        if len(node['edges'])!=1:raise ValueError('unreviewed wait loop')
        pc=int(node['edges'][0],16)
    check('CAS_retry_back_edge',lock[pc]['op']=='beqz' and '0x4037f5e8' in lock[pc]['edges'])
    check('one_CAS_per_retry',sum('<esp_cpu_compare_and_set>' in lock[x]['operands'] for x in loop)==1)
    check('no_countdown_in_forever_retry',not any(lock[x]['op'].startswith(('rsr.ccount','addi','loop')) for x in loop))
    check('reset_flash',e.get_section(syms['esp_task_wdt_reset']['st_shndx']).name=='.flash.text')
    check('lock_IRAM',e.get_section(syms['xPortEnterCriticalTimeout']['st_shndx']).name=='.iram0.text')
    (output/'reachable.json').write_text(json.dumps({n:list(g.values()) for n,g in graphs.items()},indent=2)+'\n')
    (output/'reachable.txt').write_text('\n\n'.join(n+'\n'+'\n'.join(
        f"{pc:08x}: {x['op']} {x['operands']}" for pc,x in sorted(g.items())) for n,g in graphs.items())+'\n')
    result=dict(ELF_sha256=d['ELF_sha256'],checks=checks,
        critical_retry=dict(addresses=[hex(x) for x in loop],instructions_excluding_CAS_body=len(loop),
                            iterations_bound_known=False),
        task_source_sha256=d['build']['source_sha256']['experiments/s3_raw_tasks.c'],
        conclusion='A finite registration list does not bound reset duration: its critical entry uses WAIT_FOREVER. This is an unproved bound, not proof of actual infinite waiting.',
        required=['bound concurrent lock-holder critical duration including Flash/PSRAM stalls',
                  'bound higher-level IRQ interference and all other users of this lock',
                  'bound acquisition retry/CAS latency and post-lock SDK path',
                  'include the complete reset call in the core0 last-poll to next-poll gap'],
        hardware_executed=False,WCET_proven=False,receiver_adopted=False)
    (output/'wait-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return any(not c['passed'] for c in checks)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--toolchain',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();raise SystemExit(audit(a.profile,a.toolchain.resolve(),a.output))

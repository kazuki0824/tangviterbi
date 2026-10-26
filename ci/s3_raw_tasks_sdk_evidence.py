"""Source identity, task state ABI and scoped TWDT allocations; no WCET proof."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]


def report(profile, commit):
    d = json.loads((profile/'result.json').read_text())
    raw = gzip.decompress((profile/'s3_raw_probe.elf.gz').read_bytes())
    elf = ELFFile(io.BytesIO(raw))
    symbols = {s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
    checks = []
    def check(name, passed):
        checks.append(dict(name=name, passed=bool(passed)))
    check('ELF_hash', hashlib.sha256(raw).hexdigest() == d['ELF_sha256'])
    check('SDK_static_checks', d['all_static_checks_pass'])
    for path in ('experiments/s3_raw_tasks.c','experiments/s3_raw_tasks.h',
                 'experiments/s3_cycle_clock.c','experiments/s3_native_capture.c',
                 'experiments/s3_parallel_pack.c','experiments/s3_parallel_spi.c',
                 'experiments/s3_raw_probe/main/raw_probe.c'):
        expected = hashlib.sha256(subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT)).hexdigest()
        check('source_'+path, expected == d['build']['source_sha256'].get(path))
    allocations = {}
    for name in ('raw_runtime','raw_runtime_args'):
        s = symbols[name]
        allocations[name] = dict(address=hex(s['st_value']),bytes=s['st_size'])
        check('internal_'+name, 0x3fc88000 <= s['st_value'] and s['st_value']+s['st_size'] <= 0x3fcb0000)
    entry = symbols['s3_raw_task_entry']
    check('task_entry_IRAM', elf.get_section(entry['st_shndx']).name.startswith('.iram'))
    found = {n:set() for n in ('twdt_entry','twdt_obj')}
    for unit in elf.get_dwarf_info().iter_CUs():
        for die in unit.iter_DIEs():
            a = die.attributes.get('DW_AT_name')
            size = die.attributes.get('DW_AT_byte_size')
            if a and size and a.value.decode(errors='replace') in found:
                found[a.value.decode()].add(size.value)
    check('TWDT_ABI_unambiguous', all(len(s)==1 for s in found.values()))
    if not all(len(s)==1 for s in found.values()):
        raise ValueError(found)
    types = {n:next(iter(s)) for n,s in found.items()}
    # Do not silently assume calloc always stays in internal RAM. These are
    # total requested-byte minima. Actual heap placement/rounding is unproved.
    watchdog = dict(types=types, steady_two_task_entries_min_bytes=2*(types['twdt_entry']+4),
                    two_idle_plus_two_task_transition_min_bytes=4*(types['twdt_entry']+4),
                    watchdog_object_min_bytes=types['twdt_obj']+4,
                    inherited_TWDT_interrupt_handle_and_vector_not_included=True,
                    all_calloc_internal_proven=False,
                    complete_heap_proven=False)
    return dict(commit=commit,ELF_sha256=d['ELF_sha256'],checks=checks,
                allocations=allocations,task_entry_code_bytes=entry['st_size'],
                SDK_static_check_count=len(d['checks']),symbols=d['symbols'],watchdog=watchdog,
                runtime_executed_on_target=False,WCET_proven=False,receiver_adopted=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--commit',required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    r = report(a.profile,a.commit)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
    raise SystemExit(any(not c['passed'] for c in r['checks']))

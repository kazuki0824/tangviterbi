"""Audit the candidate clock's actual SDK binary; instructions are not cycles."""
import argparse
import gzip
import hashlib
import json
import os
import io
from pathlib import Path
import re
import subprocess
from elftools.elf.elffile import ELFFile
from ci.s3_pack_cfg_audit import graph

ROOT = Path(__file__).resolve().parents[1]


def run(profile, toolchain, commit, output):
    output.mkdir(parents=True, exist_ok=True)
    data = gzip.decompress((profile/'s3_raw_probe.elf.gz').read_bytes())
    result = json.loads((profile/'result.json').read_text())
    config = json.loads(gzip.decompress((profile/'sdkconfig.json.gz').read_bytes()))
    elfpath = ROOT/'build/cycle-clock-audit.elf'
    elfpath.parent.mkdir(exist_ok=True)
    elfpath.write_bytes(data)
    checks = []
    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))
    digest = hashlib.sha256(data).hexdigest()
    check('ELF_hash', digest == result['ELF_sha256'])
    check('SDK_static_checks', result['all_static_checks_pass'])
    paths = ['experiments/s3_cycle_clock.c', 'experiments/s3_cycle_clock.h',
             'experiments/s3_raw_probe/main/raw_probe.c',
             'experiments/s3_native_capture.c', 'experiments/s3_parallel_pack.c']
    for path in paths:
        expected = hashlib.sha256(subprocess.check_output(['git', 'show', commit+':'+path], cwd=ROOT)).hexdigest()
        check('source_'+path, result['build']['source_sha256'].get(path) == expected)
    check('240MHz_two_cores_PM_disabled', config['ESP_DEFAULT_CPU_FREQ_MHZ'] == 240
          and not config['FREERTOS_UNICORE'] and not config['PM_ENABLE'])
    with elfpath.open('rb') as f:
        elf = ELFFile(f)
        symbols = {s.name: (int(s['st_value']), int(s['st_size']), s['st_shndx'])
                   for s in elf.get_section_by_name('.symtab').iter_symbols()}
        start, size, section = symbols['s3_cycle_clock_read']
        check('read_IRAM', elf.get_section(section).name.startswith('.iram'))
    state, state_size, _ = symbols['raw_cycle_clocks']
    check('two_private_states_internal', 0x3fc88000 <= state and state+state_size <= 0x3fcb0000
          and state_size == 48)
    env = os.environ.copy()
    env['XTENSA_GNU_CONFIG'] = str(toolchain/'lib/xtensa_esp32s3.so')
    nodes = graph(elfpath, str(toolchain/'bin/xtensa-esp-elf-objdump'), env, start, size)
    # The pinned compiler inlines advance. Reject hidden helper calls or loops
    # instead of assuming they are free. All graph successors must be decoded.
    check('no_calls_or_hardware_loops', all(n['call'] is None and not n['op'].startswith('loop') for n in nodes.values()))
    check('one_CCOUNT_read', sum(n['op'] == 'rsr.ccount' for n in nodes.values()) == 1)
    active, lengths = set(), {}
    def longest(pc):
        if pc in active:
            raise ValueError('clock CFG cycle')
        if pc in lengths:
            return lengths[pc]
        active.add(pc)
        lengths[pc] = 1+max((longest(int(e, 16)) for e in nodes[pc]['edges']), default=0)
        active.remove(pc)
        return lengths[pc]
    count = longest(start)
    check('acyclic_all_nodes_reachable', len(lengths) == len(nodes))
    init_start, init_size, _ = symbols['s3_cycle_clock_init']
    init_nodes = graph(elfpath, str(toolchain/'bin/xtensa-esp-elf-objdump'), env,
                       init_start, init_size)
    elf = ELFFile(io.BytesIO(data))
    sequence = []
    pc, previous = init_start, None
    while True:
        n = init_nodes[pc]
        if n['op'] == 'rsr.ccount':
            sequence.append('CCOUNT')
        if n['call'] is not None:
            # The pinned build calls IRAM esp_timer through a flash literal.
            if n['op'] != 'callx8' or not previous or previous['op'] != 'l32r':
                raise ValueError('unreviewed calibration call')
            if previous['operands'].split(',')[0].strip() != n['operands'].strip():
                raise ValueError('calibration call register mismatch')
            address = int(re.search(r', ([0-9a-f]+) <', previous['operands'])[1], 16)
            section = next(s for s in elf.iter_sections()
                           if s['sh_addr'] <= address < s['sh_addr']+s['sh_size'])
            at = address-section['sh_addr']
            target = int.from_bytes(section.data()[at:at+4], 'little')
            if target != symbols['esp_timer_get_time'][0]:
                raise ValueError('unexpected calibration callee')
            sequence.append('SYSTIMER')
        if len(n['edges']) != 1:
            break
        previous, pc = n, int(n['edges'][0], 16)
    check('startup_observation_order', sequence == ['SYSTIMER', 'CCOUNT', 'SYSTIMER', 'CCOUNT', 'SYSTIMER'])
    report = dict(commit=commit, ELF_sha256=digest, checks=checks,
                  SDK_static_checks=len(result['checks']),
                  runtime_read=dict(address=hex(start), bytes=size, reachable_instructions=len(nodes),
                                    maximum_path_instructions=count, CCOUNT_reads=1,
                                    calls=0, CFG_cycles=0, hardware_loop_instructions=0),
                  private_state_bytes=state_size, startup_observation_order=sequence,
                  symbols=result['symbols'],
                  clock_WCET_proven=False, hardware_executed=False, receiver_adopted=False,
                  exclusions=['instruction latency, memory/bus stalls, interrupt/window exceptions',
                              'caller cost, drift/continuous-clock contract, missed full wraps',
                              'startup calibration runtime; this audit covers receiver-time read only'])
    (output/'sdk-audit.json').write_text(json.dumps(report, indent=2)+'\n')
    (output/'clock-cfg.json').write_text(json.dumps(list(nodes.values()), indent=2)+'\n')
    (output/'clock-reachable.txt').write_text('\n'.join(
        f"{pc:08x}: {n['op']} {n['operands']}" for pc, n in sorted(nodes.items()))+'\n')
    print(json.dumps(report, indent=2))
    return any(not c['passed'] for c in checks)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--toolchain', type=Path, required=True)
    p.add_argument('--commit', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    raise SystemExit(run(a.profile, a.toolchain.resolve(), a.commit, a.output))

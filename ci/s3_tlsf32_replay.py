"""Replay a declared startup allocation projection with the pinned 32-bit TLSF.

Requires C compiler supporting -m32 objects (no 32-bit libc), unicorn and
pyelftools. It does NOT emulate Xtensa, ESP-IDF startup or undocumented PHY.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TLSF_COMMIT = '2867f6883a12920b1969ff9624c0ab0e4185c2ce'
TLSF_FILES = ('tlsf.c', 'include/tlsf.h', 'tlsf_block_functions.h', 'tlsf_control_functions.h')


def emulate(path):
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_INTR
    from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX,
                                  UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP)
    from elftools.elf.elffile import ELFFile
    machine = Uc(UC_ARCH_X86, UC_MODE_32)
    chunks = []
    exits = []
    with path.open('rb') as source:
        elf = ELFFile(source)
        if elf.elfclass != 32 or elf['e_machine'] != 'EM_386':
            raise ValueError('32-bit i386 replay ELF required')
        for segment in elf.iter_segments():
            if segment['p_type'] == 'PT_LOAD' and segment['p_memsz']:
                address = segment['p_vaddr']
                first = address & ~4095
                end = (address + segment['p_memsz'] + 4095) & ~4095
                machine.mem_map(first, end - first)
                machine.mem_write(address, segment.data())
        entry = elf['e_entry']
    machine.mem_map(0x70000000, 0x10000)
    machine.reg_write(UC_X86_REG_ESP, 0x7000fff0)

    def interrupt(uc, interrupt_number, _):
        if interrupt_number != 128:
            raise RuntimeError(f'unexpected interrupt {interrupt_number}')
        call = uc.reg_read(UC_X86_REG_EAX)
        arg = uc.reg_read(UC_X86_REG_EBX)
        if call == 4 and arg == 1:
            pointer = uc.reg_read(UC_X86_REG_ECX)
            size = uc.reg_read(UC_X86_REG_EDX)
            chunks.append(bytes(uc.mem_read(pointer, size)))
            uc.reg_write(UC_X86_REG_EAX, size)
        elif call == 1:
            exits.append(arg)
            uc.emu_stop()
        else:
            raise RuntimeError(f'unexpected syscall {call}/{arg}')

    machine.hook_add(UC_HOOK_INTR, interrupt)
    machine.emu_start(entry, 0)
    output = b''.join(chunks).decode()
    if exits != [0]:
        raise RuntimeError(f'replay aborted: {exits}: {output}')
    return json.loads(output)


def prepare_sources(directory):
    manifest = json.loads((ROOT / 'ci/s3_tlsf32_sources.json').read_text())
    for relative in TLSF_FILES:
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        expected = manifest['tlsf'][relative]
        if not path.exists():
            url = f'https://raw.githubusercontent.com/espressif/tlsf/{TLSF_COMMIT}/{relative}'
            path.write_bytes(urllib.request.urlopen(url, timeout=60).read())
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'source hash mismatch: {relative}')
    return manifest


def run(output, source_dir=None):
    directory = ROOT / 'build/s3-tlsf32'
    directory.mkdir(parents=True, exist_ok=True)
    source_dir = source_dir or directory / 'tlsf'
    manifest = prepare_sources(source_dir)
    cases = []
    inputs = {}
    for profile in ('n16r8', 'n16r8-late-stacks'):
        path = ROOT / 'reports/s3-raw-sdk' / profile / 'result.json'
        result = json.loads(path.read_text())
        inputs[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        config_path = path.parent / 'sdkconfig.json.gz'
        config = json.loads(gzip.decompress(config_path.read_bytes()))
        inputs[str(config_path.relative_to(ROOT))] = hashlib.sha256(config_path.read_bytes()).hexdigest()
        # Do not silently reuse the projection for changed task layouts.
        if result['sizes']['StaticTask_t'] != 340 or result['startup']['startup_task_count'] != 6:
            raise ValueError('unsupported startup ABI')
        if result['startup']['stack_lower_bound'] != {'main': 8704, 'esp_timer': 4096, 'IPC_two_cores': 2560, 'idle_two_cores': 3072}:
            raise ValueError('unsupported startup stack sizes')
        if config.get('FREERTOS_WATCHPOINT_END_OF_STACK') or config.get('COMPILER_OPTIMIZATION_NONE') or config.get('APPTRACE_ENABLE'):
            raise ValueError('unmodeled idle stack overhead')
        for configured_main in (8192, 6144, 4096, 3584):
            for records in (False, True):
                early = result['startup']['early_regions']
                lengths = [int(b, 16) - int(a, 16) for a, b in early]
                # Initial registered heap array contains both early, all late,
                # and one RTC region. Target DWARF heap_t_=36.
                count = len(early) + len(result['startup']['late_regions']) + 1
                cases.append(dict(name=f'{profile}-main{configured_main}-records{int(records)}',
                                  lower=lengths[0], upper=lengths[1],
                                  rtc=result['startup']['RTC_generous_bytes'],
                                  main_stack=configured_main + 512,
                                  heap_records=36 * count if records else 0))
    header = 'static const struct scenario scenarios[]={\n'
    for c in cases:
        header += '{"%s",%d,%d,%d,%d,%d},\n' % tuple(c.values())
    (directory / 'scenarios.h').write_text(header + '};\n')
    binary = directory / 'replay32'
    command = ['cc', '-m32', '-O2', '-static', '-nostdlib', '-fno-pie', '-no-pie',
               '-fno-builtin', '-fno-stack-protector', '-I', str(ROOT / 'ci/tlsf32_shim'),
               '-I', str(source_dir / 'include'), '-I', str(directory), '-Wl,-e,_start',
               str(ROOT / 'ci/s3_tlsf32_replay.c'), str(source_dir / 'tlsf.c'), '-o', str(binary)]
    subprocess.run(command, check=True)
    traces = emulate(binary)
    import unicorn
    import elftools
    result = dict(scope=__doc__, input_sha256=inputs, scenarios=cases, traces=traces,
                  source_manifest=manifest, tool_versions={
                      'cc': subprocess.check_output(['cc', '--version'], text=True).splitlines()[0],
                      'unicorn': unicorn.__version__, 'pyelftools': elftools.__version__},
                  replay_ELF_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                  heap_order=['DIRAM ascending original arena size', 'RTC'],
                  target_heap_record_bytes=36, target_multi_heap_info_bytes=20,
                  excluded=['other constructors and libc allocations/frees',
                            'PSRAM registration heap record and startup allocations',
                            'interrupt/watchdog and timer implementation allocations',
                            'full heap_caps hardware alignment wrapper',
                            'PHY/SPI runtime allocations', 'late heap and DMA pool activation'],
                  hardware_boot_executed=False, receiver_adopted=False,
                  conclusion_scope='Known-allocation projection only. Missing allocations/frees can change heap selection; failure is not a universal boot impossibility proof. Smaller main stacks are unbuilt sensitivity cases, not measured safe stack sizes.')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/s3-startup-order/result.json')
    parser.add_argument('--tlsf-source', type=Path)
    args = parser.parse_args()
    result = run(args.output, args.tlsf_source)
    for trace in result['traces']:
        failed = next((e['name'] for e in trace['events'] if e['heap'] is None), '-')
        print(trace['name'], trace['projected_trace_pass'], failed)

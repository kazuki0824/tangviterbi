"""Audit the built core1 candidate; enumerate all static checks before failing.

A successful build/static audit does not certify hardware WCET or RF continuity.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
from elftools.elf.elffile import ELFFile


def audit(build, project, idf, out, objdump):
    out.mkdir(parents=True, exist_ok=True)
    raw = (build/'s3_queue_memory_probe.elf').read_bytes()
    elf = ELFFile(io.BytesIO(raw))
    symbols = {s.name: s for s in elf.get_section_by_name('.symtab').iter_symbols()}
    config = json.loads((build/'config/sdkconfig.json').read_text())
    checks = []
    def check(name, fn):
        try:
            value = fn()
            checks.append(dict(name=name, ok=bool(value), error=None))
        except Exception as error:
            checks.append(dict(name=name, ok=False, error=str(error)))
    def data(name):
        symbol = symbols[name]
        section = elf.get_section(symbol['st_shndx'])
        offset = symbol['st_value'] - section['sh_addr']
        return section.data()[offset:offset+symbol['st_size']]
    check('timer_task_core1', lambda: config['ESP_TIMER_TASK_AFFINITY'] == 1)
    check('timer_irq_core1_only', lambda: config.get('ESP_TIMER_ISR_AFFINITY_CPU1') and not config.get('ESP_TIMER_ISR_AFFINITY_CPU0') and not config.get('ESP_TIMER_ISR_AFFINITY_NO_AFFINITY'))
    check('PLL_tracking_preserved_1Hz', lambda: not config.get('ESP_PHY_DISABLE_PLL_TRACK') and config['ESP_PHY_PLL_TRACK_PERIOD_MS'] == 1000)
    check('dual_core_N16R8', lambda: not config.get('FREERTOS_UNICORE') and config['SPIRAM_MODE_OCT'] and config['ESPTOOLPY_FLASHSIZE_16MB'])
    check('compiled_contract', lambda: struct.unpack('<7I', data('s3_queue_core1_contract')) == (1, 1, 22, 6, 2048, 1000, 16384))
    # Decode actual SDK init descriptor: fn pointer, uint16 core mask, uint16 stage.
    check('linked_timer_init_mask_core1', lambda: struct.unpack('<IHH', data('esp_system_init_fn_esp_timer_init_os')) == (symbols['__esp_system_init_fn_esp_timer_init_os']['st_value'], 2, 1))
    phy = (idf/'components/esp_phy/src/phy_common.c').read_text()
    timer = (idf/'components/esp_timer/src/esp_timer.c').read_text()
    args = phy.split('const esp_timer_create_args_t phy_track_pll_timer_args = {', 1)[1].split('};', 1)[0]
    check('PHY_default_task_dispatch_no_skip', lambda: '.callback = &phy_track_pll_timer_callback' in args and 'dispatch_method' not in args and 'skip_unhandled_events' not in args)
    check('PHY_lock_in_callback', lambda: '_lock_acquire(&phy_lock);' in phy and '_lock_release(&phy_lock);' in phy)
    check('timer_dispatch_uses_configured_core', lambda: '&s_timer_task, CONFIG_ESP_TIMER_TASK_AFFINITY)' in timer)
    check('timer_backlog_not_skipped', lambda: 'it->alarm += it->period;' in timer and '(*callback)(arg);' in timer)
    disassemblies = {}
    names = ('create_tasks', 'esp_timer_init', '__esp_system_init_fn_esp_timer_init_os',
             'phy_track_pll_timer_callback', 'phy_track_pll', 'phy_param_track_tot',
             'rfpll_cap_track', 'wait_hw_freq_busy', 'rfpll_cap_correct',
             'ram_phy_dis_hw_set_freq', 'ram_phy_en_hw_set_freq', 'ram_write_pll_cap',
             's3_raw_task_entry', 'poll_rf', 'feed', 'pack_slice', 's3_pp_step_impl')
    for name in names:
        def decode(name=name):
            if name not in symbols:
                return False
            disassemblies[name] = subprocess.check_output([objdump, '-d', '--disassemble='+name,
                str(build/'s3_queue_memory_probe.elf')], text=True).replace(str(build/'s3_queue_memory_probe.elf'), 'core1.elf')
            return '<'+name+'>:' in disassemblies[name]
        check('linked_'+name, decode)
    def busy_loop():
        text = disassemblies['wait_hw_freq_busy']
        target = int(re.search(r'bltz\s+a9, ([0-9a-f]+)', text)[1], 16)
        start = symbols['wait_hw_freq_busy']['st_value']
        decoded = subprocess.check_output([objdump, '-d', '--start-address='+hex(target),
            '--stop-address='+hex(start+32), str(build/'s3_queue_memory_probe.elf')], text=True).replace(str(build/'s3_queue_memory_probe.elf'), 'core1.elf')
        disassemblies['wait_branch_target'] = decoded
        return target == start+12 and all(s in decoded for s in ('memw', 'l32i.n', 'bltz', 'esp_rom_delay_us')) and bool(re.search(r'movi.n\s+a10, 50', decoded))
    check('unbounded_busy_loop_and_conditional_50us_remain', busy_loop)
    (out/'candidate.dis').write_text('\n'.join(disassemblies.values()))
    source_paths = ['components/esp_phy/src/phy_common.c', 'components/esp_phy/src/phy_init.c',
                    'components/esp_timer/src/esp_timer.c', 'components/esp_timer/Kconfig',
                    'components/esp_system/include/esp_task.h', 'components/esp_system/include/esp_private/startup_internal.h']
    for source in source_paths:
        target = out/'sdk-source'/source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((idf/source).read_bytes())
    provenance = json.loads((project/'provenance.json').read_text())
    for relative, digest in provenance['generated_sha256'].items():
        check('generated_identity_'+relative, lambda relative=relative, digest=digest: hashlib.sha256((project/relative).read_bytes()).hexdigest() == digest)
    result = dict(scope=__doc__, static_checks=checks, all_static_checks_pass=all(c['ok'] for c in checks),
        ELF_sha256=hashlib.sha256(raw).hexdigest(), idf_commit=subprocess.check_output(['git', '-C', str(idf), 'rev-parse', 'HEAD'], text=True).strip(),
        sdk_sources_sha256={p:hashlib.sha256((idf/p).read_bytes()).hexdigest() for p in source_paths},
        generated=provenance, timer_priority=22, receiver_priorities_allowed=list(range(1,22)),
        affects_all_esp_timer_callbacks=True,
        completion_gates={
            'core1_build_and_static_binding': all(c['ok'] for c in checks),
            'hardware_callback_WCET': False, 'RF_continuity_during_PLL_tracking': False,
            'board_runtime_affinity_observed': False},
        unresolved=['PHY mutex wait bound', 'hardware busy-clear bound', 'conditional correction reachability and ROM callees',
                    'callback backlog and other timer callbacks', 'RF phase/frequency/sample continuity during correction',
                    'target cycle timing and shared memory contention'],
        hardware_executed=False, hardware_WCET_us=None, item_1_completed=False,
        receiver_adopted=False, safe_to_flash=False)
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('static_checks','completion_gates','item_1_completed')}, indent=2))
    return result['all_static_checks_pass']

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    for name in ('build','project','idf','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--objdump', default=shutil.which('xtensa-esp32s3-elf-objdump') or shutil.which('xtensa-esp-elf-objdump'))
    args=parser.parse_args()
    raise SystemExit(0 if audit(args.build,args.project,args.idf,args.output,args.objdump) else 1)

"""Scoped TWDT heap and list-traversal budget, not a complete heap/WCET proof."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def report(tasks, memory):
    manifest = json.loads((ROOT/'reports/s3-raw-tasks/sources.json').read_text())
    checks = []
    for name, record in manifest.items():
        digest = hashlib.sha256((ROOT/'reports/s3-raw-tasks/sources'/name).read_bytes()).hexdigest()
        checks.append(dict(name='source_'+name, passed=digest == record['sha256']))
    checks.append(dict(name='same_ELF', passed=tasks['ELF_sha256'] == memory['input_sha256']['ELF']))
    checks.append(dict(name='scoped_runtime_audit', passed=memory['all_scoped_checks_pass']))
    checks.append(dict(name='scoped_task_audit', passed=all(c['passed'] for c in tasks['checks'])))
    types = tasks['watchdog']['types']
    entry = types['twdt_entry'] + 4
    obj = types['twdt_obj'] + 4
    handle = memory['types']['intr_handle_data_t'] + 4
    vector = memory['types']['vector_desc_t'] + 4
    # No APPTRACE wrapper or retention allocations in the pinned probe config.
    # Ordinary calloc prefers internal for <=16384B but can fall back to PSRAM.
    # Therefore only the IRQ handle/vector are unconditionally internal here.
    phase_entries = {'SPI_live': 2, 'PHY_calibration': 2, 'steady': 2,
                     'receiver_start_overlap': 4, 'idle_restore_overlap': 3}
    cases = {}
    for vectors in ('existing_vectors', 'fresh_vectors'):
        irq = handle + (vector if vectors == 'fresh_vectors' else 0)
        phases = {}
        for phase, count in phase_entries.items():
            base_phase = phase if phase in memory['phases'][vectors] else 'steady'
            base = memory['phases'][vectors][base_phase]['remaining_internal_upper_bound']
            phases[phase] = dict(known_entry_count=count, extra_entry_count='M >= 0',
                known_TWDT_total_min_bytes=obj+count*entry+irq,
                forced_internal_min_bytes=irq,
                remaining_internal_upper_bound_after_forced_TWDT=base-irq,
                conditional_all_known_TWDT_calloc_internal_upper_bound=base-irq-obj-count*entry)
        cases[vectors] = phases
    return dict(ELF_sha256=tasks['ELF_sha256'], checks=checks,
        ABI_with_minimum_headers=dict(entry=entry, object=obj, IRQ_handle=handle, fresh_vector=vector),
        phases=cases,
        conditions=['successful TWDT hardware interrupt allocation',
                    'two idle registrations initially; receiver task entries are newly added',
                    'PHY calibration completes before receiver task creation',
                    'peer unregisters before owner restores the two idle registrations',
                    'existing_vectors/fresh_vectors apply consistently to SPI and TWDT',
                    'M other registrations are not charged in numeric subtotals'],
        calloc_placement='16-byte objects prefer internal with limit 16384 but DEFAULT fallback may use PSRAM',
        extra_entry_min_bytes=entry,
        receive_reset_list_visits=dict(entries='N = 2 + M', lookup='N',
            clear_flags_when_all_reset='N', maximum_total='2*N = 4 + 2*M',
            note='SDK reset has no allocation; list traversal is inside a shared spinlock'),
        excluded=['other TWDT registrations', 'allocator rounding/fragmentation',
                  'lazy libc/logging/hook allocations', 'all other omissions in runtime-memory.json',
                  'spinlock/IRQ arrival bounds and PSRAM access latency'],
        complete_heap_proven=False, WCET_proven=False, receiver_adopted=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tasks',type=Path,required=True)
    p.add_argument('--memory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    r = report(json.loads(a.tasks.read_text()),json.loads(a.memory.read_text()))
    a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({'checks':r['checks'],'ABI':r['ABI_with_minimum_headers'],'fresh':r['phases']['fresh_vectors']},indent=2))
    raise SystemExit(any(not c['passed'] for c in r['checks']))

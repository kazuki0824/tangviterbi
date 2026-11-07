#!/usr/bin/env python3
"""Reproduce the candidate C audit. This is NOT S3 execution or a WCET model.

Target instructions are compiled and decoded by the Espressif toolchain. A small
TRM semantic interpreter checks their arithmetic/addressing. Independent host C
and direct convolution check streaming boundaries. Timing is instruction count
at an explicit, optimistic one instruction/cycle assumption.
"""
import argparse
import collections
import ctypes as C
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'experiments/t_preprocess_capacity'
BUILD = ROOT / 'build/t-halfband-capacity'
DEFAULT_OUTPUT = ROOT / 'reports/s3-t-preprocess-capacity/halfband'
C_FLAGS = ['-O2', '-fno-tree-slp-vectorize', '-std=c11',
           '-Wall', '-Wextra', '-Werror']
COEFFICIENTS = [-18, 0, 68, 0, -182, 0, 404, 0, -803, 0, 1533, 0,
                -3116, 0, 10305, 16384, 10305, 0, -3116, 0, 1533, 0,
                -803, 0, 404, 0, -182, 0, 68, 0, -18]


def command(args, env=None):
    return subprocess.run(args, cwd=ROOT, env=env, check=True,
                          text=True, capture_output=True).stdout


def repo_path(path):
    """Use ROOT-relative artifact/source names, independently of the shell cwd."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


class Checks:
    """Collect independent groups even after a failure; block only dependants."""
    def __init__(self):
        self.rows = []
        self.values = {}

    def run(self, name, function, requires=()):
        statuses = {row['id']: row['status'] for row in self.rows}
        blocked = [f'{item}={statuses.get(item, "NOT_RUN")}' for item in requires
                   if statuses.get(item) != 'PASS']
        if blocked:
            self.rows.append({'id': name, 'status': 'BLOCKED',
                              'reason': 'Dependencies not passed: ' + ', '.join(blocked)})
            return None
        try:
            value = function()
        except Exception as error:
            detail = str(error) or repr(error)
            if isinstance(error, subprocess.CalledProcessError):
                detail += '\n' + (error.stderr or error.stdout or '')
            self.rows.append({'id': name, 'status': 'FAIL',
                              'reason': f'{type(error).__name__}: {detail.strip()}'})
            return None
        self.values[name] = value
        self.rows.append({'id': name, 'status': 'PASS'})
        return value


def coefficient_contract():
    source = (SOURCE / 'halfband31.c').read_text()
    body = re.search(r'hb31_coefficients\[31\]\s*=\s*\{(.*?)\};', source, re.S)
    assert body, 'Cannot locate the candidate coefficient table'
    actual = [int(value.strip()) for value in body[1].split(',') if value.strip()]
    assert actual == COEFFICIENTS, 'C table differs from the independently pinned oracle'
    assert actual == actual[::-1]
    assert actual[15] == 16384
    assert all(actual[i] == 0 for i in range(1, 31, 2) if i != 15)
    assert 512 * sum(map(abs, actual)) < (1 << 39)
    return {'coefficients': 31, 'nonzero_coefficients': 17,
            'same_receiver_quality_proved': False}


def instructions(text, symbol):
    body = text.split('<' + symbol + '>:', 1)[1].split('\n\n', 1)[0]
    result = []
    for line in body.splitlines():
        match = re.match(r'\s*([0-9a-f]+):\s+[0-9a-f]+\s+(\S+)(?:\s+(.*))?$', line)
        if match and not match[2].startswith('.'):
            args = [a.strip() for a in (match[3] or '').split(',') if a.strip()]
            result.append((int(match[1], 16), match[2], args))
    assert result and all(op != 'excw' for _, op, _ in result), 'S3 config needed for objdump'
    return result


def dependency_schedule(code):
    """TRM v1.8 Table 1.7-2 register interlocks, NOT a full CPU simulator.

    Def means available at the END of that stage; use is at its BEGINNING.
    A reader must issue D=max(def_stage-use_stage+1,0) cycles after its writer.
    Explicit/implicit PIE registers are covered. ADDI is conservatively treated
    as AR use at decode stage 0 / result at ALU stage 1; no extra stall is needed
    by this schedule even with that earlier-than-bypass read assumption.
    """
    def operands(op, args):
        uses, definitions = {}, {}
        if op in ('entry', 'retw.n', 'nop', 'nop.n'):
            return uses, definitions
        if op in ('addi', 'addi.n'):
            definitions[args[0]], uses[args[1]] = 1, 0
        elif op == 'ee.zero.qacc':
            definitions.update(QACC_H=1, QACC_L=1)
        elif op in ('ee.vld.128.ip', 'ee.ld.128.usar.ip'):
            destination, pointer, _ = args
            uses[pointer], definitions[pointer], definitions[destination] = 1, 1, 2
            if op == 'ee.ld.128.usar.ip':
                definitions['SAR_BYTE'] = 1
        elif op == 'ee.src.q':
            destination, low, high = args
            uses.update({low: 1, high: 1, 'SAR_BYTE': 1})
            definitions[destination] = 1
        elif op == 'ee.vmulas.s16.qacc':
            uses.update({args[0]: 1, args[1]: 1, 'QACC_H': 2, 'QACC_L': 2})
            definitions.update(QACC_H=2, QACC_L=2)
        elif op == 'ee.srcmb.s16.qacc':
            destination, amount, zero = args
            assert zero == '0'
            uses.update({amount: 1, 'QACC_H': 1, 'QACC_L': 1})
            definitions.update({destination: 1, 'QACC_H': 1, 'QACC_L': 1})
        elif op == 'ee.vst.128.ip':
            source, pointer, _ = args
            uses.update({source: 1, pointer: 1})
            definitions[pointer] = 1
        else:
            raise AssertionError('Unclassified dependency opcode: ' + op)
        return uses, definitions

    last_def = {}
    next_issue, stalls, edges = 0, 0, 0
    classes, conflicts = collections.Counter(), []
    for index, (address, op, args) in enumerate(code):
        uses, definitions = operands(op, args)
        required_issue = next_issue
        reasons = []
        for register, use_stage in uses.items():
            if register not in last_def:
                continue  # Function inputs; caller/entry timing is outside this audit.
            writer, writer_issue, def_stage = last_def[register]
            distance = max(def_stage - use_stage + 1, 0)
            required = writer_issue + distance
            edges += 1
            kind = 'QR' if register.startswith('q') else 'AR' if register.startswith('a') else register
            classes[f'{kind}:def{def_stage}->use{use_stage}'] += 1
            required_issue = max(required_issue, required)
            if required > next_issue:
                reasons.append({'register': register, 'writer_index': writer,
                                'required_issue_distance': distance})
        waiting = required_issue - next_issue
        if waiting:
            conflicts.append({'instruction_index': index, 'opcode': op,
                              'stall_cycles': waiting, 'reasons': reasons})
        stalls += waiting
        for register, stage in definitions.items():
            last_def[register] = (index, required_issue, stage)
        next_issue = required_issue + 1
    return {'instruction_count': len(code), 'required_operand_stall_cycles': stalls,
            'issue_span_cycles_in_this_model': next_issue,
            'dependency_edges_checked': edges, 'dependency_classes': dict(classes),
            'conflicts': conflicts}


def legacy_kernel_schedule():
    """Previous opcode order, pinned by its former assembly source SHA256.

    This is a regression fixture, not a second executable implementation. Its
    original pointer/add/load order has 17 coefficient-load and 12 SRC load-use
    interlocks that an arithmetic-only interpreter could not expose.
    """
    rows = [('entry', ['a1', '32']), ('ee.zero.qacc', [])]
    for _ in range(4):
        rows += [('ee.vld.128.ip', ['q2', 'a2', '0']),
                 ('ee.vld.128.ip', ['q3', 'a4', '16']),
                 ('ee.vmulas.s16.qacc', ['q2', 'q3']),
                 ('addi.n', ['a2', 'a2', '4'])]
        for _ in range(3):
            rows += [('ee.ld.128.usar.ip', ['q0', 'a2', '16']),
                     ('ee.vld.128.ip', ['q1', 'a2', '-16']),
                     ('ee.src.q', ['q2', 'q0', 'q1']),
                     ('ee.vld.128.ip', ['q3', 'a4', '16']),
                     ('ee.vmulas.s16.qacc', ['q2', 'q3']),
                     ('addi.n', ['a2', 'a2', '4'])]
    rows += [('ee.vld.128.ip', ['q2', 'a3', '0']),
             ('ee.vld.128.ip', ['q3', 'a4', '0']),
             ('ee.vmulas.s16.qacc', ['q2', 'q3']), ('nop.n', []), ('nop.n', []),
             ('ee.srcmb.s16.qacc', ['q2', 'a6', '0']),
             ('ee.vst.128.ip', ['q2', 'a5', '0']), ('retw.n', [])]
    return [(i, op, args) for i, (op, args) in enumerate(rows)]


def check_kernel_hazards(code):
    current = dependency_schedule(code)
    assert current['required_operand_stall_cycles'] == 0, json.dumps(current['conflicts'])
    legacy = dependency_schedule(legacy_kernel_schedule())
    assert legacy['instruction_count'] == 98
    assert legacy['required_operand_stall_cycles'] == 29
    cases = [
        ('adjacent_load_to_MAC', [('ee.vld.128.ip', ['q3', 'a4', '0']),
                                 ('ee.vmulas.s16.qacc', ['q2', 'q3'])], 1),
        ('adjacent_QACC_to_SRCMB', [('ee.vmulas.s16.qacc', ['q2', 'q3']),
                                  ('ee.srcmb.s16.qacc', ['q2', 'a6', '0'])], 1),
        ('adjacent_SRCMB_to_store', [('ee.srcmb.s16.qacc', ['q2', 'a6', '0']),
                                   ('ee.vst.128.ip', ['q2', 'a5', '0'])], 0),
        ('adjacent_load_postincrement_to_load', [('ee.vld.128.ip', ['q0', 'a2', '16']),
                                               ('ee.vld.128.ip', ['q1', 'a2', '16'])], 0),
        ('adjacent_SAR_BYTE_to_SRC', [('ee.ld.128.usar.ip', ['q0', 'a2', '16']),
                                    ('ee.src.q', ['q2', 'q4', 'q5'])], 0),
    ]
    for name, rows, expected in cases:
        result = dependency_schedule([(i, op, args) for i, (op, args) in enumerate(rows)])
        assert result['required_operand_stall_cycles'] == expected, name
    return {
        'current': current, 'legacy_order': legacy,
        'regression_cases': len(cases),
        'legacy_assembly_source_SHA256': 'a21217b8c15a23863f2575ab950e4dfdd1411d9c3d5afdd77e001af2ce199b8b',
        'reference': 'ESP32-S3 TRM v1.8 section 1.7.1 and Table 1.7-2 (pp65-74)',
        'reference_url': 'https://documentation.espressif.com/esp32-s3_technical_reference_manual_en.pdf',
        'reference_PDF_SHA256': '4484bf8a69035ec42a731c58c64ada6fbd1f1618c5559409f134d9ea083f444f',
        'covered': 'Decoded kernel QR, QACC_H/L, SAR_BYTE, PIE postincrement AR and conservative ADDI register dependencies.',
        'excluded_scope': 'Entry/return/caller control penalties, other instruction hardware-resource conflicts, fetch/cache/memory waits, ABI window spills, interrupts and cross-core contention. Zero operand interlocks is not zero total stalls or measured WCET.',
    }


def kernel_model(code, even, odd, coefficients, shift):
    """The TRM's aligned loads, USAR+SRC, lane QACC MAC and SRCMB semantics."""
    regions = {
        0x1000: struct.pack('<40h', *even),
        0x2000: struct.pack('<8h', *odd),
        0x3000: struct.pack('<136h', *coefficients),
    }
    registers = {'a2': 0x1000, 'a3': 0x2000, 'a4': 0x3000,
                 'a5': 0x4000, 'a6': shift}
    vectors, accumulator, sar_byte, reads, writes = {}, [0] * 8, 0, [], []

    def load(address):
        address &= ~15
        for base, data in regions.items():
            if base <= address and address + 16 <= base + len(data):
                reads.append(address)
                return int.from_bytes(data[address-base:address-base+16], 'little')
        raise AssertionError(f'Out-of-buffer vector read: {address:x}')

    for _, op, args in code:
        if op in ('entry', 'retw.n', 'nop.n', 'nop'):
            continue
        if op == 'ee.zero.qacc':
            accumulator = [0] * 8
        elif op in ('addi', 'addi.n'):
            destination, source, immediate = args
            registers[destination] = registers[source] + int(immediate)
        elif op in ('ee.vld.128.ip', 'ee.ld.128.usar.ip'):
            destination, pointer, step = args
            if op == 'ee.ld.128.usar.ip':
                sar_byte = registers[pointer] & 15
            vectors[destination] = load(registers[pointer])
            registers[pointer] += int(step)
        elif op == 'ee.src.q':
            destination, low, high = args
            vectors[destination] = (((vectors[high] << 128) | vectors[low]) >>
                                    (sar_byte * 8)) & ((1 << 128) - 1)
        elif op == 'ee.vmulas.s16.qacc':
            x, y = [struct.unpack('<8h', vectors[v].to_bytes(16, 'little')) for v in args]
            accumulator = [max(-(1 << 39), min((1 << 39) - 1, a + b*c))
                           for a, b, c in zip(accumulator, x, y)]
        elif op == 'ee.srcmb.s16.qacc':
            destination, amount, zero = args
            assert zero == '0'
            accumulator = [x >> (registers[amount] & 63) for x in accumulator]
            values = [max(-32768, min(32767, x)) for x in accumulator]
            vectors[destination] = int.from_bytes(struct.pack('<8h', *values), 'little')
        elif op == 'ee.vst.128.ip':
            source, pointer, step = args
            assert registers[pointer] == 0x4000
            writes.append(vectors[source].to_bytes(16, 'little'))
            registers[pointer] += int(step)
        else:
            raise AssertionError('Unsupported target instruction: ' + op)
    assert len(writes) == 1
    return list(struct.unpack('<8h', writes[0])), reads


def check_kernel(code):
    rng = random.Random(310163)
    cases = 0
    max_read = 0
    # Both real signed10 input and wider diagnostic inputs/coefficients. The
    # diagnostic vectors test lane ordering without relying on FIR symmetry.
    for test in range(400):
        amplitude = 512 if test < 200 else 32768
        even = [rng.randrange(-amplitude, amplitude) for _ in range(40)]
        odd = [rng.randrange(-amplitude, amplitude) for _ in range(8)]
        if test == 0:
            even, odd = [-512] * 40, [-512] * 8
        elif test == 1:
            even, odd = [511] * 40, [511] * 8
        if test < 200:
            coefficients = [v for c in COEFFICIENTS[30::-2] + [COEFFICIENTS[15]] for v in [c] * 8]
        else:
            coefficients = [rng.randrange(-32768, 32768) for _ in range(136)]
        for shift in (0, 10, 15, 31):
            wanted = []
            for lane in range(8):
                total = sum(even[2*t + lane] * coefficients[8*t + lane] for t in range(16))
                total += odd[lane] * coefficients[128 + lane]
                assert abs(total) < (1 << 39)
                wanted.append(max(-32768, min(32767, total >> shift)))
            actual, reads = kernel_model(code, even, odd, coefficients, shift)
            assert actual == wanted, (test, shift, actual, wanted)
            max_read = max(max_read, max(a + 16 - 0x1000 for a in reads if a < 0x2000))
            cases += 1
    return {'cases': cases, 'comparisons_s16_lanes': cases * 8,
            'max_even_read_bytes': max_read,
            'input_read_extent_including_padding_bytes': 80,
            'target_executed': False}


def aligned_buffer(size):
    owner = C.create_string_buffer(size + 32)
    address = (C.addressof(owner) + 15) & ~15
    return owner, address


def check_streaming():
    lib = C.CDLL(str(BUILD / 'halfband31_host.so'))
    process = lib.hb31_process
    process.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_size_t,
                        C.c_void_p, C.c_uint32]
    process.restype = C.c_size_t
    coefficient_array = (C.c_int16 * 31).in_dll(lib, 'hb31_coefficients')
    assert list(coefficient_array) == COEFFICIENTS
    rng = random.Random(826064)
    calls = samples = 0
    for shift in (0, 10, 15, 31):
        state_owner, state = aligned_buffer(92)
        work_owner, work = aligned_buffer(4192)
        history = []
        for n in [8, 16, 24, 32, 64, 128, 256, 512, 1024] * 3:
            raw_owner, raw = aligned_buffer(n * 4)
            out_owner, output = aligned_buffer(n * 2 + 32)
            C.memset(output, 0xa5, n * 2 + 32)
            values = []
            words = (C.c_uint32 * n).from_address(raw)
            for k in range(n):
                i, q = rng.randrange(-512, 512), rng.randrange(-512, 512)
                if k % 4 == 0:
                    i, q = -512, 511
                elif k % 4 == 1:
                    i, q = 511, -512
                words[k] = (i & 1023) | ((q & 1023) << 10) | (rng.randrange(4096) << 20)
                values.append((i, q))
            start = len(history)
            history.extend(values)
            wanted = []
            for k in range(0, n, 2):
                for component in (0, 1):
                    total = sum(c * history[start+k-t][component]
                                for t, c in enumerate(COEFFICIENTS) if start+k-t >= 0)
                    wanted.append(max(-32768, min(32767, total >> shift)))
            assert process(state, work, raw, n, output, shift) == n // 2
            assert list((C.c_int16 * n).from_address(output)) == wanted
            assert C.string_at(output + n * 2, 32) == bytes([0xa5]) * 32
            calls += 1
            samples += n // 2
        # The invalid-input contract must not mutate state/output/workspace.
        snapshot = (C.string_at(state, 92), C.string_at(output, n*2+32), C.string_at(work, 4192))
        invalid = [(state, work, raw, n, output, 32),
                   (state, work, raw, 0, output, shift),
                   (state, work, raw, 7, output, shift),
                   (state, work, raw, 1032, output, shift),
                   (state, work+2, raw, n, output, shift),
                   (state, work, raw+2, n, output, shift),
                   (state, work, raw, n, output+2, shift),
                   (state+2, work, raw, n, output, shift),
                   (None, work, raw, n, output, shift)]
        for args in invalid:
            assert process(*args) == 0
            assert snapshot == (C.string_at(state, 92), C.string_at(output, n*2+32), C.string_at(work, 4192))
    return {'valid_calls': calls, 'complex_outputs_compared': samples,
            'invalid_calls': len(invalid) * 4, 'target_executed': False}


def instruction_counts(process, kernel, copy):
    # The valid-input path bypasses two rejection jumps and the final return-0
    # movi. Source/addresses are pinned by the audit hashes. Fail rather than
    # silently accepting a compiler CFG change.
    assert [(addr, op) for addr, op, _ in process if op == 'j'] == [(0x2c, 'j'), (0x34, 'j'), (0x12c, 'j')]
    assert next(x for x in process if x[0] == 0x130)[1:] == ('movi.n', ['a2', '0'])
    unpack = [x for x in process if 0x98 <= x[0] < 0xc0]
    caller = [x for x in process if 0xf4 <= x[0] <= 0x10c]
    assert len(unpack) == 15 and len(caller) == 11
    assert len(kernel) == 98
    assert len(copy) == 7 and copy[1][1] == 'loop'
    fixed = len(process) - len(unpack) - len(caller) - 3
    history = 4 * 3 + (15 + 8 + 15 + 8) * 4
    rows = []
    for raw_count in (8, 64, 128, 256, 512, 1024):
        output = raw_count // 2
        subtotal = fixed + history + len(unpack) * output + (len(caller) + len(kernel)) * output // 4
        rows.append({'raw_count': raw_count, 'complex_output_count': output,
                     'instructions_per_block': subtotal,
                     'M_instructions_per_s_at_16M_raw': subtotal * 16 / raw_count,
                     'single_core_service_us_at_240MHz_1inst_per_cycle': subtotal / 240,
                     'input_block_duration_us': raw_count / 16})
    return {'kernel_instructions_per_4_outputs': len(kernel),
            'unpack_instructions_per_2_raw': len(unpack),
            'caller_loop_instructions_per_4_outputs': len(caller),
            'fixed_process_instructions_per_block': fixed,
            'history_copy_instructions_per_block': history,
            'history_copies_per_block': [60, 32, 60, 32],
            'raw_input_Mbytes_per_s': 64,
            'unpacked_workspace_store_Mbytes_per_s': 64,
            'Q15_output_Mbytes_per_s': 32,
            'kernel_vector_loads_per_4_outputs': sum(op in ('ee.vld.128.ip', 'ee.ld.128.usar.ip') for _, op, _ in kernel),
            'kernel_opcode_histogram': dict(collections.Counter(op for _, op, _ in kernel)),
            'block_sizes': rows}


def spectrum():
    pass_edge = 39 / 14 + 0.1
    stop_edge = 8 - pass_edge
    p, s = [], []
    for k in range(65537):
        f = 8 * k / 65536
        h = (COEFFICIENTS[15] + 2 * sum(COEFFICIENTS[n] * math.cos(2*math.pi*f*(15-n)/16)
              for n in range(15))) / 32768
        if f <= pass_edge:
            p.append(abs(h))
        if f >= stop_edge:
            s.append(abs(h))
    return {'diagnostic_only_not_quality_equivalence': True,
            'frequency_points': 65537, 'input_rate_Mcomplex_s': 16,
            'pass_edge_MHz': pass_edge, 'stop_edge_MHz': stop_edge,
            'pass_ripple_peak_to_peak_dB': 20 * math.log10(max(p) / min(p)),
            'stop_attenuation_min_on_grid_dB': -20 * math.log10(max(s)),
            'Q15_coefficient_sum': sum(COEFFICIENTS),
            'Q15_coefficient_abs_sum': sum(map(abs, COEFFICIENTS)),
            'signed10_accumulator_abs_bound': 512 * sum(map(abs, COEFFICIENTS)),
            'shift10_output_abs_bound': (512 * sum(map(abs, COEFFICIENTS)) + 1023) // 1024,
            'group_delay_us': 15 / 16}


def conditional_capacity(counts):
    costs = counts['block_sizes'][-1]['M_instructions_per_s_at_16M_raw']
    api = (32 + 0.01) * 4800 / 32768
    retained_rf = 57.375
    return {
        'candidate_preprocessing': costs, 'retained_legacy_RF_and_adjustment': retained_rf,
        'legacy_API_32KiB_20us_for_32MBps': api,
        'base_before_legacy_transfer_copy': costs + retained_rf + api,
        'plus_distinct_transfer_copy_1cycle_per_byte': costs + retained_rf + api + 32,
        'plus_distinct_transfer_copy_2cycle_per_byte': costs + retained_rf + api + 64,
        'aggregate_capacity': 480,
        'transfer_copy_overlap': 'Charge 32/64 only if a distinct payload pass remains. Output conversion/store is already in the kernel.',
        'ideal_unimplemented_two_stage_split': {
            'prepare_Mcycles_s': costs - 218,
            'kernel_and_caller_Mcycles_s': 218,
            'kernel_and_caller_at_alpha_1_1_Mcycles_s': 239.8,
            'legacy_core1_tick_100Hz_times_1696cycles_Mcycles_s': 0.1696,
            'core1_remaining_after_alpha_1_1_and_tick_cycles_s': 30400,
            'handoff_sync_IRQ_window_spills_and_memory_stalls_included': False,
            'per_core_deadlines_proved': False,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--toolchain', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT,
                        help='Report directory; relative paths are resolved against repository ROOT')
    args = parser.parse_args()
    toolchain = args.toolchain
    if not toolchain.is_absolute():
        toolchain = ROOT / toolchain
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['XTENSA_GNU_CONFIG'] = str(toolchain / 'lib/xtensa_esp32s3.so')
    gcc = str(toolchain / 'bin/xtensa-esp-elf-gcc')
    objdump = str(toolchain / 'bin/xtensa-esp-elf-objdump')
    source_c, source_asm = [repo_path(SOURCE / name) for name in ('halfband31.c', 'halfband31.S')]
    object_c, object_asm, host_library = [repo_path(BUILD / name) for name in
                                        ('halfband31.o', 'halfband31_asm.o', 'halfband31_host.so')]
    checks = Checks()
    checks.run('build_directory', lambda: BUILD.mkdir(parents=True, exist_ok=True))
    version = checks.run('target_toolchain_version', lambda: command([gcc, '--version'], env).splitlines()[0])
    # Build groups do not depend on version detection or one another. A failed
    # current build never authorizes reuse of an object left by an earlier run.
    checks.run('target_c_build', lambda: command([gcc, *C_FLAGS, '-c', source_c, '-o', object_c], env),
               requires=('build_directory',))
    checks.run('target_asm_build', lambda: command([gcc, '-c', source_asm, '-o', object_asm], env),
               requires=('build_directory',))
    checks.run('host_c_build', lambda: command(['gcc', *C_FLAGS, '-shared', '-fPIC', source_c,
                                               repo_path(SOURCE / 'halfband31_host.c'), '-o', host_library]),
               requires=('build_directory',))
    c_dis = checks.run('target_c_disassembly', lambda: command([objdump, '-dr', object_c], env),
                       requires=('target_c_build',))
    asm_dis = checks.run('target_asm_disassembly', lambda: command([objdump, '-dr', object_asm], env),
                         requires=('target_asm_build',))
    process = checks.run('target_c_decode', lambda: instructions(c_dis, 'hb31_process'),
                          requires=('target_c_disassembly',))
    kernel = checks.run('target_kernel_decode', lambda: instructions(asm_dis, 'hb31_qacc4'),
                         requires=('target_asm_disassembly',))
    copy = checks.run('target_history_decode', lambda: instructions(asm_dis, 'hb31_copy_words'),
                       requires=('target_asm_disassembly',))
    coefficient_check = checks.run('coefficient_contract', coefficient_contract)
    kernel_tests = checks.run('target_kernel_semantics', lambda: check_kernel(kernel),
                              requires=('target_kernel_decode',))
    kernel_hazards = checks.run('target_kernel_operand_interlocks', lambda: check_kernel_hazards(kernel),
                                requires=('target_kernel_decode',))
    host_tests = checks.run('host_streaming_oracle', check_streaming,
                            requires=('host_c_build',))
    counts = checks.run('instruction_counts', lambda: instruction_counts(process, kernel, copy),
                         requires=('target_c_decode', 'target_kernel_decode', 'target_history_decode'))
    spectral = checks.run('spectrum_and_integer_bound', spectrum, requires=('coefficient_contract',))
    capacity = checks.run('conditional_CPU_arithmetic', lambda: conditional_capacity(counts),
                           requires=('instruction_counts', 'target_kernel_operand_interlocks'))
    dis_path = output / 'halfband31.dis'
    dis_text = (c_dis or '# target C disassembly unavailable; see check status\n')
    dis_text += (asm_dis or '# target asm disassembly unavailable; see check status\n')
    checks.run('write_disassembly_artifact', lambda: dis_path.write_text(dis_text))
    source_files = [SOURCE / name for name in
                    ('halfband31.c', 'halfband31.h', 'halfband31.S', 'halfband31_host.c')]
    source_files.append(Path(__file__).resolve())
    hashes = checks.run('source_hashes', lambda: {
        repo_path(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files})
    dis_hash = checks.run('disassembly_hash', lambda: {
        repo_path(dis_path): hashlib.sha256(dis_path.read_bytes()).hexdigest()},
        requires=('write_disassembly_artifact',))
    summary = {status: sum(row['status'] == status for row in checks.rows)
               for status in ('PASS', 'FAIL', 'BLOCKED')}
    audit_passed = not summary['FAIL'] and not summary['BLOCKED']
    result = {
        'status': 'candidate_CPU_condition_only_not_receiver_pass',
        'audit_status': 'PASS' if audit_passed else 'FAIL',
        'check_summary': summary, 'checks': checks.rows,
        'non_fail_fast': True,
        'target_compiler': version, 'c_flags': C_FLAGS,
        'instruction_model': 'one-instruction-per-cycle baseline after audited operand interlocks are removed; control/resource/fetch/memory/ABI/IRQ costs are outside this baseline, not WCET',
        'kernel_model_tests': kernel_tests, 'host_streaming_tests': host_tests,
        'kernel_operand_interlocks': kernel_hazards,
        'coefficient_contract': coefficient_check,
        'instructions': counts, 'coefficients_Q15': COEFFICIENTS, 'spectrum': spectral,
        'memory': {'state_bytes': 92, 'workspace_bytes': 4192,
                   'coefficient_vectors_bytes': 272, 'raw_1024_bytes': 4096,
                   'output_512_bytes': 2048, 'double_buffering_included': False},
        'conditional_CPU_Mcycles_s_at_1024_raw': capacity,
        'accepted_same_quality': False, 'target_runtime_executed': False,
        'continuous_RF_or_per_core_deadlines_proved': False,
        'FPGA_64_over_63_resampler_implemented_or_sized': False,
        'source_hashes_SHA256': hashes,
        'disassembly_hashes_SHA256': dis_hash,
        'temporary_build_directory': repo_path(BUILD),
        'primary_references': [
            'https://documentation.espressif.com/esp32-s3_technical_reference_manual_en.pdf',
            'https://github.com/espressif/esp-dl/blob/5989f4a38f553235daf4da8a3de33a1acefe2196/esp-dl/dl/base/isa/tie728/dl_tie728_s16.S',
        ],
    }
    result_path = output / 'halfband_results.json'
    result_path.write_text(json.dumps(result, indent=2) + '\n')
    for row in checks.rows:
        print(f'{row["status"]:7} {row["id"]}' + (': ' + row['reason'] if 'reason' in row else ''))
    print(f'Audit {result["audit_status"]}: {summary}; {repo_path(result_path)}')
    return 0 if audit_passed else 1


if __name__ == '__main__':
    sys.exit(main())

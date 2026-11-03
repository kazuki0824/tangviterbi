#!/usr/bin/env python3
"""Compile and audit a bounded two-core halfband CPU candidate.

The actual C ownership state machine is used by host arithmetic and event tests.
The event test has explicit external-service/interrupt/transport contracts; it
does not pretend to be the existing SDK/native-RF receiver. Every independent
check and every event scenario is collected, including deliberate overloads.
"""
import argparse
import collections
import ctypes as C
import functools
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import random
import re
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from ci.t_halfband_capacity_audit import (Checks, COEFFICIENTS, C_FLAGS,
    aligned_buffer, check_kernel, check_kernel_hazards, instructions, repo_path)

SOURCE = ROOT / 'experiments/t_preprocess_capacity'
DEFAULT_OUTPUT = ROOT / 'reports/s3-t-preprocess-capacity/pipeline'
RAW = 1024
OUTPUT_BYTES = 2048
FRAME = 16384
FRAME_COUNT = 8
PERIOD = 15360  # 1024 raw samples at 16 MS/s, 240 MHz cycles.
SLICE_LIMIT = 20000
POLL_LIMIT = 30000  # 2000 raw samples: threshold-to-late margin, not any time.
# 303280 cycles from native switch, less an explicitly assumed 125us handoff.
BANK_RELATIVE_DEADLINE = 303280 - 30000


def command(args, env=None):
    return subprocess.run([str(x) for x in args], cwd=ROOT, env=env,
                          check=True, capture_output=True, text=True).stdout


def charged(instruction_count, alpha):
    """Exact ceil; binary floating point must not add an accidental cycle."""
    assert alpha in (1.0, 1.1)
    return (instruction_count * (10 if alpha == 1.0 else 11) + 9) // 10


def open_library(path):
    lib = C.CDLL(str(path))
    for name, args in {
        'hbpipe_init': [C.c_void_p, C.c_uint32],
        'hbpipe_produce': [C.c_void_p, C.c_void_p, C.c_void_p],
        'hbpipe_work': [C.c_void_p],
        'hbpipe_reap': [C.c_void_p, C.POINTER(C.c_void_p), C.POINTER(C.c_uint32)],
        'hbpipe_status': [C.c_void_p, C.c_uint],
    }.items():
        f = getattr(lib, name)
        f.argtypes, f.restype = args, C.c_int
    lib.hbpipe_size.argtypes, lib.hbpipe_size.restype = [], C.c_size_t
    return lib


def host_oracle(path):
    lib = open_library(path)
    rng = random.Random(3101024)
    errors, rows = [], []
    for shift in (0, 10, 15, 31):
        holder, pipe = aligned_buffer(lib.hbpipe_size())
        assert lib.hbpipe_init(pipe, shift) == 0
        retained, expected, outputs = [], [], []
        produced = consumed = reaped = 0
        busy_checks = empty_checks = 0
        for block in range(40):
            raw_owner, raw = aligned_buffer(RAW * 4)
            output_owner, output = aligned_buffer(OUTPUT_BYTES + 32)
            C.memset(output, 0xa5, OUTPUT_BYTES + 32)
            words = (C.c_uint32 * RAW).from_address(raw)
            values = []
            for k in range(RAW):
                i, q = rng.randrange(-512, 512), rng.randrange(-512, 512)
                if (block + k) % 31 == 0:
                    i, q = -512, 511
                words[k] = (i & 1023) | ((q & 1023) << 10) | (rng.randrange(4096) << 20)
                values.append((i, q))
            outputs.append((output_owner, output))
            retained.append((raw_owner, raw, values))
        history = [v for _, _, values in retained for v in values]
        for k in range(0, len(history), 2):
            for component in (0, 1):
                total = sum(coef * history[k-t][component]
                            for t, coef in enumerate(COEFFICIENTS) if k >= t)
                expected.append(max(-32768, min(32767, total >> shift)))
        # Two producer calls intentionally advance history before the first
        # worker runs. A delayed reaper additionally tests the DONE lease.
        while reaped < len(retained):
            while produced < len(retained):
                before = C.string_at(pipe, lib.hbpipe_size())
                raw = retained[produced][1]
                rc = lib.hbpipe_produce(pipe, raw, outputs[produced][1])
                if rc == 2:
                    busy_checks += 1
                    if C.string_at(pipe, lib.hbpipe_size()) != before:
                        errors.append(f'shift{shift}: BUSY mutated producer state')
                    break
                if rc != 0:
                    raise AssertionError(f'producer returned {rc}')
                # Raw is no longer owned by the pipeline after produce returns.
                C.memset(raw, 0x5a, RAW * 4)
                produced += 1
            out, seq = C.c_void_p(), C.c_uint32()
            if reaped == consumed:
                if lib.hbpipe_reap(pipe, C.byref(out), C.byref(seq)) != 1:
                    errors.append(f'shift{shift}: premature reap was accepted')
                empty_checks += 1
            if consumed < produced:
                if lib.hbpipe_work(pipe) != 0:
                    errors.append(f'shift{shift}: worker failed')
                consumed += 1
            if consumed > reaped:
                rc = lib.hbpipe_reap(pipe, C.byref(out), C.byref(seq))
                if rc or seq.value != reaped or out.value != outputs[reaped][1]:
                    errors.append(f'shift{shift}: reap/order/pointer mismatch')
                actual = list((C.c_int16 * RAW).from_address(outputs[reaped][1]))
                if actual != expected[reaped*RAW:(reaped+1)*RAW]:
                    errors.append(f'shift{shift}: block{reaped} convolution mismatch')
                if C.string_at(outputs[reaped][1]+OUTPUT_BYTES, 32) != b'\xa5'*32:
                    errors.append(f'shift{shift}: output overrun')
                reaped += 1
        if lib.hbpipe_work(pipe) != 1:
            errors.append(f'shift{shift}: empty worker accepted')
        empty_checks += 1
        before = C.string_at(pipe, lib.hbpipe_size())
        dummy_owner, dummy = aligned_buffer(4096)
        invalid = ((None, dummy, dummy), (pipe, None, dummy),
                   (pipe, dummy, None), (pipe, dummy+1, dummy),
                   (pipe, dummy, dummy+2), (pipe+4, dummy, dummy))
        for args in invalid:
            if lib.hbpipe_produce(*args) != 3:
                errors.append(f'shift{shift}: invalid producer accepted')
        if C.string_at(pipe, lib.hbpipe_size()) != before:
            errors.append(f'shift{shift}: invalid call mutated state')
        rows.append({'shift': shift, 'blocks': reaped,
                     'complex_outputs_compared': reaped * 512,
                     'busy_checks': busy_checks, 'empty_checks': empty_checks,
                     'invalid_calls': len(invalid)})
    if errors:
        raise AssertionError('; '.join(errors))
    return {'rows': rows, 'errors': errors, 'target_executed': False,
            'history_advanced_before_previous_worker': True,
            'raw_overwritten_after_produce': True,
            'host_pipe_bytes': lib.hbpipe_size()}


def decoded(text, name):
    return [x for x in instructions(text, name) if x[1] != 'ill']


def target_counts(c_text, asm_text):
    functions = {name: decoded(c_text, name) for name in (
        'hbpipe_unpack', 'hbpipe_prefix', 'hbpipe_suffix',
        'hbpipe_produce', 'hbpipe_work', 'hbpipe_reap')}
    kernel = decoded(asm_text, 'hb31_qacc4')
    copy = decoded(asm_text, 'hb31_copy_words')
    assert len(kernel) == 98
    assert [op for _, op, _ in copy] == [
        'entry', 'loop', 'l32i.n', 's32i.n', 'addi.n', 'addi.n', 'retw.n']
    reloc = {}
    for line in c_text.splitlines():
        m = re.search(r'^\s*([0-9a-f]+): R_XTENSA_SLOT0_OP\s+(\S+)', line)
        if m:
            reloc[int(m[1], 16)] = m[2]
    address_names = {code[0][0]: name for name, code in functions.items()}

    def destination(args):
        return int(args[-1].split()[0], 16)

    def helper(name, repetitions, hardware=False):
        code = functions[name]
        if hardware:
            loops = [x for x in code if x[1] == 'loop']
            assert len(loops) == 1
            at, _, args = loops[0]
            end = destination(args)
            body = [x for x in code if at < x[0] < end]
            setup = [x for x in code if x[0] < at and x[1].startswith('movi')
                     and x[2][0] == args[0]]
            assert setup and int(setup[-1][2][1], 0) == repetitions
        else:
            backs = [x for x in code if x[1].startswith('b') and destination(x[2]) < x[0]]
            assert len(backs) == 1
            end, op, args = backs[0]
            assert op == 'bne'
            start = destination(args)
            body = [x for x in code if start <= x[0] <= end]
        body_addresses = {x[0] for x in body}
        fixed = [x for x in code if x[0] not in body_addresses]
        assert not any(op.startswith('b') or op == 'j' for _, op, _ in fixed)
        calls = [x for x in body if x[1].startswith('call')]
        if hardware:
            assert not calls and len(body) == 15
        else:
            assert len(calls) == 1 and reloc[calls[0][0]] == 'hb31_qacc4'
        own = len(fixed) + len(body) * repetitions
        callee = len(calls) * repetitions * len(kernel)
        return {'own_instructions': own, 'callee_instructions': callee,
                'total_instructions': own + callee,
                'body_instructions': len(body), 'iterations': repetitions,
                'fixed_instructions': len(fixed)}

    helpers = {'hbpipe_unpack': helper('hbpipe_unpack', 512, True),
               'hbpipe_prefix': helper('hbpipe_prefix', 8),
               'hbpipe_suffix': helper('hbpipe_suffix', 120)}

    def path_count(name):
        code = functions[name]
        by_addr = {x[0]: x for x in code}
        following = {code[i][0]: code[i+1][0] for i in range(len(code)-1)}
        calls = [x for x in code if x[1].startswith('call')]
        copy_calls = [x[0] for x in calls if reloc.get(x[0]) == 'hb31_copy_words']
        if name == 'hbpipe_produce':
            assert len(copy_calls) == 4
        else:
            assert not copy_calls
        copy_cost, copy_words = {}, []
        count_register = None
        for addr, opcode, args in code:
            if opcode.startswith('movi') and args[0] == 'a12':
                count_register = int(args[1], 0)
            if opcode.startswith('call'):
                if addr in copy_calls:
                    assert count_register in (8, 15), 'unexpected history copy argument'
                    copy_words.append(count_register)
                    copy_cost[addr] = 3 + 4*count_register
                count_register = None
        if copy_calls:
            assert copy_words == [15, 8, 15, 8]
        callees = {}
        for addr, op, args in calls:
            symbol = reloc.get(addr)
            if symbol == 'hb31_copy_words':
                callees[addr] = (symbol, copy_cost[addr])
            else:
                target = destination(args)
                symbol = address_names[target]
                callees[addr] = (symbol, helpers[symbol]['total_instructions'])

        @functools.lru_cache(None)
        def visit(addr):
            _, op, args = by_addr[addr]
            own, callee = 1, callees.get(addr, ('', 0))[1]
            if op.startswith('ret'):
                return own + callee, own, callee, (addr,)
            if op == 'j':
                choices = [destination(args)]
            elif op.startswith('b'):
                choices = [following[addr], destination(args)]
                assert all(x > addr for x in choices), 'outer operation unexpectedly loops'
            else:
                choices = [following[addr]]
            best = max((visit(x) for x in choices), key=lambda x: x[0])
            return own+callee+best[0], own+best[1], callee+best[2], (addr,)+best[3]
        total, own, callee, witness = visit(code[0][0])
        return {'total_instructions': total, 'own_instructions': own,
                'callee_instructions': callee,
                'witness': [hex(x) for x in witness],
                'callees': {hex(a): {'symbol': s, 'instructions': n}
                            for a, (s, n) in callees.items()}}

    outer = {name: path_count(name) for name in (
        'hbpipe_produce', 'hbpipe_work', 'hbpipe_reap')}
    c0 = outer['hbpipe_produce']['total_instructions'] + outer['hbpipe_reap']['total_instructions']
    c1 = outer['hbpipe_work']['total_instructions']
    return {'helpers': helpers, 'operations': outer,
            'core0_instructions_per_block_including_reap': c0,
            'core1_instructions_per_block': c1,
            'aggregate_Minstructions_s': (c0+c1)/64,
            'old_hb31_process_caller_added': False,
            'instruction_cost_unit': 'one executed instruction; callee entry/return included once'}


def capacity(counts):
    rows = []
    op = counts['operations']
    for alpha in (1.0, 1.1):
        fees = {name: charged(v['total_instructions'], alpha) for name, v in op.items()}
        c0 = fees['hbpipe_produce'] + fees['hbpipe_reap']
        c1 = fees['hbpipe_work']
        rows.append({'alpha': alpha, 'fees_cycles': fees,
            'core_Mcycles_s': [c0/64, c1/64],
            'external_allowance_Mcycles_s': [(PERIOD-c0)/64, (PERIOD-c1)/64],
            'external_allowance_us_per_64us': [(PERIOD-c0)/240, (PERIOD-c1)/240],
            'nonpreempted_produce_us': fees['hbpipe_produce']/240,
            'nonpreempted_worker_us': fees['hbpipe_work']/240,
            'additional_interruption_before_83_333us_slice_limit_us': [
                (SLICE_LIMIT-fees['hbpipe_produce'])/240,
                (SLICE_LIMIT-fees['hbpipe_work'])/240],
            'cpu_only_necessary_condition': c0 < PERIOD and c1 < PERIOD,
            'eligible_after_known_control_hazard_gate': alpha == 1.1,
            'alpha_1_0_scope': 'Instruction-only reference; known control bubbles are omitted, so not an eligible physical timing claim.' if alpha == 1.0 else None})
    return rows


def scalar_control_gate(counts, c_text, asm_text):
    """Check that alpha1.1 does not fall below known control/data costs.

    TRM 1.7.3 has a two-cycle taken-control bubble. Calls and returns are
    conservatively charged the same two cycles. A load immediately consumed
    by a store gets an extra cycle allowance even where store-stage forwarding
    could avoid it; this is not a memory/MMIO/window WCET proof.
    """
    names = ('hbpipe_unpack', 'hbpipe_prefix', 'hbpipe_suffix',
             'hbpipe_produce', 'hbpipe_work', 'hbpipe_reap')
    code = {name: decoded(c_text, name) for name in names}
    paths = {}
    for name in ('hbpipe_produce', 'hbpipe_work', 'hbpipe_reap'):
        by_addr = {x[0]: x for x in code[name]}
        paths[name] = [by_addr[int(a, 16)] for a in counts['operations'][name]['witness']]

    def controls(path, complete_code):
        following = {complete_code[i][0]: complete_code[i+1][0]
                     for i in range(len(complete_code)-1)}
        total = 0
        for i, (addr, op, args) in enumerate(path):
            if op.startswith(('call', 'ret')) or op == 'j':
                total += 2
            elif op.startswith('b') and i+1 < len(path):
                if path[i+1][0] != following[addr]:
                    total += 2
        return total

    outer = {name: controls(path, code[name]) for name, path in paths.items()}
    # The compiled helper loop bodies and counts were independently extracted
    # above. Hardware LOOP has no explicit branch per iteration.
    kernel = decoded(asm_text, 'hb31_qacc4')
    kernel_ret = sum(op.startswith('ret') for _, op, _ in kernel)*2
    copy = decoded(asm_text, 'hb31_copy_words')
    copy_ret = sum(op.startswith('ret') for _, op, _ in copy)*2
    helper_control = {}
    for name, repeats in (('hbpipe_prefix', 8), ('hbpipe_suffix', 120)):
        calls = sum(op.startswith('call') for _, op, _ in code[name])
        returns = sum(op.startswith('ret') for _, op, _ in code[name])
        branches = sum(op.startswith('b') for _, op, _ in code[name])
        assert (calls, returns, branches) == (1, 1, 1)
        helper_control[name] = 2*(calls*repeats+returns+branches*(repeats-1)) + repeats*kernel_ret
    helper_control['hbpipe_unpack'] = sum(op.startswith('ret') for _, op, _ in code['hbpipe_unpack'])*2
    control = [outer['hbpipe_produce']+outer['hbpipe_reap']+4*copy_ret+
               helper_control['hbpipe_unpack']+helper_control['hbpipe_prefix'],
               outer['hbpipe_work']+helper_control['hbpipe_suffix']]

    def adjacent_load_uses(path):
        found = []
        for left, right in zip(path, path[1:]):
            a, op, args = left
            b, nextop, nextargs = right
            if not op.startswith(('l32i', 'l32r', 'l16', 'l8')):
                continue
            register = args[0]
            if nextop.startswith(('s32i', 's16i', 's8i', 'b')):
                uses = nextargs
            elif nextop.startswith(('ret', 'call')) or nextop == 'j':
                uses = []
            else:
                uses = nextargs[1:]
                if nextop.startswith(('moveqz', 'movnez')):
                    uses = nextargs
            if register in uses:
                found.append({'load': hex(a), 'consumer': hex(b),
                              'register': register, 'consumer_opcode': nextop})
        return found
    adjacent = {name: adjacent_load_uses(paths.get(name, code[name])) for name in names}
    assert not any(adjacent[name] for name in (
        'hbpipe_unpack', 'hbpipe_prefix', 'hbpipe_suffix', 'hbpipe_work'))
    assert len(adjacent['hbpipe_produce']) == 1
    assert len(adjacent['hbpipe_reap']) == 3
    copy_dependencies = adjacent_load_uses(copy)
    assert len(copy_dependencies) == 1 and copy_dependencies[0]['consumer_opcode'].startswith('s32i')
    scalar = [len(adjacent['hbpipe_produce'])+len(adjacent['hbpipe_reap'])+15+8+15+8, 0]
    baseline = [counts['core0_instructions_per_block_including_reap'],
                counts['core1_instructions_per_block']]
    inspected = [baseline[i]+control[i]+scalar[i] for i in (0, 1)]
    alpha11 = [charged(counts['operations']['hbpipe_produce']['total_instructions'], 1.1)+
               charged(counts['operations']['hbpipe_reap']['total_instructions'], 1.1),
               charged(counts['operations']['hbpipe_work']['total_instructions'], 1.1)]
    assert control == [78, 726]
    assert all(a <= b for a, b in zip(inspected, alpha11))
    return {'control_extra_cycles_per_block': control,
            'scalar_adjacent_allowance_cycles_per_block': scalar,
            'inspected_cycles_per_core_block': inspected,
            'alpha_1_1_cycles_per_core_block': alpha11,
            'alpha_1_0_is_instruction_only_reference': True,
            'outer_control_cycles': outer, 'helper_control_cycles': helper_control,
            'scalar_adjacent_pairs': adjacent,
            'copy_load_store_allowance_words': 46,
            'reference': 'ESP32-S3 TRM v1.8 sections 1.7.1 and 1.7.3; store-use +1 and call/return +2 are conservative allowances.',
            'not_bounded': ['memory/cache/MMIO/memw wait', 'register-window exceptions',
                            'interrupt/task PIE context preservation', 'final scheduler costs']}


def event_case(lib, counts, settings):
    """Actual C slot operations, with separately declared time/arrival contracts.

    Calls occur at completion events, so READY/DONE never become visible early.
    A no-op arithmetic callee is linked ONLY for this test: slot/history/atomic
    C is unchanged, while scalar FIR arithmetic was independently checked above.
    """
    alpha = settings['alpha']
    fees = {k: charged(v['total_instructions'], alpha)
            for k, v in counts['operations'].items()}
    blocks = settings.get('blocks', 4096)
    batch = settings['batch_blocks']
    horizon = blocks * PERIOD
    limit = horizon + 5_000_000
    holders = []
    for size in (lib.hbpipe_size(), RAW*4, FRAME*FRAME_COUNT):
        owner, address = aligned_buffer(size)
        holders.append((owner, address))
    pipe, raw, arena = [x[1] for x in holders]
    assert lib.hbpipe_init(pipe, 10) == 0
    pending = collections.deque()
    external = [collections.deque(), collections.deque()]
    active = [None, None]
    generation = [0, 0]
    ready_to_work = collections.deque()
    ready_to_reap = collections.deque()
    frames = [None] * FRAME_COUNT
    raw_owned = {}
    releases = {}
    events, serial = [], 0
    totals = [0, 0]
    event_counts = collections.Counter()
    faults = collections.Counter()
    first_fault = {}
    max_slice = [0, 0]
    max_latency = 0
    max_producer_start_lag = max_reap_latency = 0
    max_poll_gap = 0
    last_poll = None
    max_raw_owned = max_frames = 0
    produced = worked = reaped = 0
    last_link_end = 0
    next_frame_id = 0

    def push(time, kind, payload=None):
        nonlocal serial
        serial += 1
        heapq.heappush(events, (int(time), serial, kind, payload))

    def fault(name, time):
        faults[name] += 1
        first_fault.setdefault(name, time/240)

    for start in range(0, blocks, batch):
        push(start*PERIOD, 'arrival', (start, min(batch, blocks-start)))
    for block in range(blocks):
        push(block*PERIOD, 'external', None)
    for core, fee in ((0, 1846), (1, 1696)):
        for time in range(2_400_000, horizon+1, 2_400_000):
            push(time, 'interrupt', (core, fee, 'tick'))
        # Steady-state phase: a WDT update may fall within a short observation.
        for time in range(24_000_000, horizon+1, 600_000_000):
            push(time, 'interrupt', (core, 516, 'wdt'))
    if settings.get('periodic_us', 0):
        begin = int(settings.get('periodic_phase_us', 5000)*240)
        for time in range(begin, horizon+1, 240_000_000):
            push(time, 'interrupt', (settings['periodic_core'],
                 int(settings['periodic_us']*240), 'declared_periodic'))

    def start_job(core, now, kind, duration, payload=None):
        generation[core] += 1
        token = generation[core]
        active[core] = {'kind': kind, 'start': now, 'end': now+duration,
                        'payload': payload, 'token': token}
        totals[core] += duration
        event_counts[f'core{core}_{kind}'] += 1
        push(now+duration, 'finish', (core, token))

    def dispatch(now):
        nonlocal max_frames, max_producer_start_lag
        for core in (0, 1):
            if active[core] is not None:
                continue
            if external[core]:
                duration = external[core].popleft()
                start_job(core, now, 'external', duration)
                continue
            if core == 0:
                if ready_to_reap:
                    job = ready_to_reap.popleft()
                    start_job(0, now, 'reap', fees['hbpipe_reap'], job)
                elif pending and lib.hbpipe_status(pipe, produced & 1) == 0:
                    job, bank = pending[0]
                    fi, group = (job//8) % FRAME_COUNT, job//8
                    if job % 8 == 0:
                        if frames[fi] is not None:
                            continue
                        frames[fi] = {'group': group, 'completed': 0}
                    elif frames[fi] is None or frames[fi]['group'] != group:
                        raise AssertionError('output frame ownership/order mismatch')
                    pending.popleft()
                    max_producer_start_lag = max(max_producer_start_lag, now-releases[job])
                    output = arena + fi*FRAME + (job % 8)*OUTPUT_BYTES
                    max_frames = max(max_frames, sum(x is not None for x in frames))
                    start_job(0, now, 'produce', fees['hbpipe_produce'], (job, bank, output))
            elif ready_to_work:
                job, bank, output = ready_to_work.popleft()
                start_job(1, now, 'work', fees['hbpipe_work'], (job, bank, output))

    while events:
        now, _, kind, payload = heapq.heappop(events)
        if now > limit:
            fault('drain_horizon_exceeded', now)
            break
        if kind == 'arrival':
            start, count = payload
            bank = start//batch
            raw_owned[bank] = count
            max_raw_owned = max(max_raw_owned, len(raw_owned))
            # One of the three physical native banks remains reserved for RF.
            if len(raw_owned) > 2:
                fault('more_than_two_released_raw_banks_plus_active_RF_bank', now)
            for job in range(start, start+count):
                pending.append((job, bank))
                releases[job] = now
        elif kind == 'external':
            for core in (0, 1):
                external[core].append(int(settings[f'external{core}_us_per_64us']*240))
        elif kind == 'interrupt':
            core, duration, name = payload
            event_counts[f'core{core}_{name}'] += 1
            if active[core] is None:
                start_job(core, now, 'interrupt_only', duration)
            else:
                active[core]['end'] += duration
                generation[core] += 1
                active[core]['token'] = generation[core]
                totals[core] += duration
                push(active[core]['end'], 'finish', (core, generation[core]))
        elif kind == 'dma_ready':
            fi, group = payload
            assert frames[fi] and frames[fi]['group'] == group
            start = max(now, last_link_end)
            last_link_end = start + math.ceil(FRAME*240/settings['drain_MBps'])
            # API/IRQ dispatch is bounded by the next external reservation.
            push(last_link_end+PERIOD, 'dma_complete', (fi, group))
        elif kind == 'dma_complete':
            fi, group = payload
            assert frames[fi] and frames[fi]['group'] == group
            frames[fi] = None
            event_counts['dma_frames_completed'] += 1
        elif kind == 'finish':
            core, token = payload
            task = active[core]
            if task is None or token != task['token']:
                continue
            active[core] = None
            operation = task['kind']
            if operation in ('produce', 'work'):
                elapsed = now-task['start']
                max_slice[core] = max(max_slice[core], elapsed)
                if elapsed > SLICE_LIMIT:
                    fault(f'core{core}_slice_over_20000_cycles', now)
            if operation == 'produce':
                job, bank, output = task['payload']
                assert job == produced
                assert lib.hbpipe_produce(pipe, raw, output) == 0
                produced += 1
                raw_owned[bank] -= 1
                if not raw_owned[bank]:
                    del raw_owned[bank]
                if now-releases[job] > BANK_RELATIVE_DEADLINE:
                    fault('raw_copy_after_declared_bank_deadline', now)
                ready_to_work.append((job, bank, output))
            elif operation == 'work':
                job, bank, output = task['payload']
                assert job == worked
                assert lib.hbpipe_work(pipe) == 0
                worked += 1
                max_latency = max(max_latency, now-releases[job])
                if now-releases[job] > BANK_RELATIVE_DEADLINE:
                    fault('output_after_declared_bank_deadline', now)
                ready_to_reap.append((job, bank, output))
            elif operation == 'reap':
                job, bank, output = task['payload']
                out, seq = C.c_void_p(), C.c_uint32()
                assert lib.hbpipe_reap(pipe, C.byref(out), C.byref(seq)) == 0
                assert seq.value == job == reaped and out.value == output
                reaped += 1
                max_reap_latency = max(max_reap_latency, now-releases[job])
                # Physical raw-bank release needs produce to finish. Requiring
                # output completion AND handoff by the same time is a stricter
                # additional contract of this candidate, not a native ABI fact.
                if now-releases[job] > BANK_RELATIVE_DEADLINE:
                    fault('output_reap_after_extra_conservative_deadline', now)
                fi = (job//8) % FRAME_COUNT
                frame = frames[fi]
                assert frame and frame['group'] == job//8
                frame['completed'] += 1
                if frame['completed'] == 8:
                    push(now+PERIOD, 'dma_ready', (fi, job//8))
            elif operation == 'external' and core == 0:
                if last_poll is not None:
                    gap = now-last_poll
                    max_poll_gap = max(max_poll_gap, gap)
                    if gap > POLL_LIMIT:
                        fault('RF_poll_gap_over_125us', now)
                last_poll = now
        # All releases/completions at one timestamp precede task dispatch.
        # An arbitrary heap insertion order must not silently change priority.
        if not events or events[0][0] != now:
            dispatch(now)
    if reaped != blocks:
        fault('not_all_blocks_reaped', limit)
    if any(frames):
        fault('output_leases_not_all_completed', limit)
    return {**settings, 'scenario_pass': not faults,
            'physical_timing_eligible_after_known_control_gate': alpha == 1.1,
            'blocks_produced_worked_reaped': [produced, worked, reaped],
            'nominal_input_horizon_s': horizon/240e6,
            'max_raw_banks_owned': max_raw_owned,
            'max_output_frames_owned': max_frames,
            'max_output_arena_bytes': max_frames*FRAME,
            'max_slice_us': [x/240 for x in max_slice],
            'max_RF_service_completion_gap_us': max_poll_gap/240,
            'max_output_latency_from_bank_release_us': max_latency/240,
            'max_producer_start_delay_from_release_us': max_producer_start_lag/240,
            'max_reap_latency_from_release_us': max_reap_latency/240,
            'fixed_64us_producer_start_guaranteed': False,
            'declared_bank_relative_deadline_us': BANK_RELATIVE_DEADLINE/240,
            'fault_counts': dict(faults), 'first_fault_time_us': first_fault,
            'event_counts': dict(event_counts),
            'charged_cycles_by_core': totals,
            'fees_cycles': fees}


def event_matrix(path, counts):
    lib = open_library(path)
    cases = []
    for alpha in (1.0, 1.1):
        for batch in (1, 11, 12):
            cases.append({'id': f'alpha{alpha}_batch{batch}', 'alpha': alpha,
                          'batch_blocks': batch, 'external0_us_per_64us': 16,
                          'external1_us_per_64us': 2, 'drain_MBps': 40})
    base = {'alpha': 1.1, 'batch_blocks': 12, 'external0_us_per_64us': 20,
            'external1_us_per_64us': 2, 'drain_MBps': 40}
    cases.append({'id': 'declared_service_candidate', **base})
    cases.append({'id': 'core0_overload', **base, 'external0_us_per_64us': 26})
    cases.append({'id': 'core1_overload', **base, 'external1_us_per_64us': 8})
    cases.append({'id': 'transport_overload', **base, 'drain_MBps': 28})
    for core in (0, 1):
        for duration in (10, 25, 50):
            for phase in (5000, 65000):
                cases.append({'id': f'periodic_core{core}_{duration}us_phase{phase}',
                              **base, 'periodic_core': core, 'periodic_us': duration,
                              'periodic_phase_us': phase})
    rows, exceptions = [], []
    for case in cases:
        try:
            rows.append(event_case(lib, counts, case))
        except Exception as exc:
            exceptions.append({'id': case['id'], 'error': repr(exc)})
            rows.append({**case, 'scenario_pass': False, 'execution_error': repr(exc)})
    expected = {r['id']: r for r in rows}
    assertions = {
        'declared_service_candidate_passes': expected['declared_service_candidate']['scenario_pass'],
        'core0_overload_rejected': not expected['core0_overload']['scenario_pass'],
        'core1_overload_rejected': not expected['core1_overload']['scenario_pass'],
        'transport_overload_rejected': not expected['transport_overload']['scenario_pass'],
        'all_scenarios_executed': len(rows) == len(cases) and not exceptions,
    }
    return {'rows': rows, 'assertions': assertions, 'exceptions': exceptions,
            'audit_pass': all(assertions.values()),
            'not_all_phase_or_unbounded_time_proof': True,
            'source_bank_contract': 'Aligned 1024-sample blocks, batches of 1, 11 or 12; 11/12 represent 11264/12288-sample release bursts. One native bank remains reserved for RF, leaving at most two released banks. Actual variable native bank boundaries/ring-wrap assembly are not implemented. A maximum 125us switch-to-handoff delay is assumed, giving 303280-30000=273280 cycles from release to the declared deadline. The physical raw deadline applies to produce completion; work completion and reap must meet the same deadline as additional conservative conditions here.',
            'external_contract': 'Every 64us reservation includes all outer dispatch/idle checks and RF/API/SDK work; actual SDK event counts are not connected. Core0 reservation completion is the assumed RF poll. Tick and WDT interrupt costs are charged separately.',
            'transport_contract': '128KiB=8 DMA frames; 8 reaped outputs/frame, bounded API dispatch one 64us reservation before start and after wire completion, declared aggregate wire MB/s. This is not an implemented SPI route.',
            'periodic_contract': 'One declared 1Hz interrupt service at each tested phase; busy-wait duration is a sensitivity parameter, not measured PHY time.'}


def target_layout(gcc, objcopy, build, env):
    source = build/'layout.c'
    source.write_text('#include "halfband_pipeline.h"\n#include <stddef.h>\n'
                      'const unsigned layout[]={sizeof(hbpipe),sizeof(hbpipe_slot),'
                      'sizeof(hb31_workspace),sizeof(hb31_state),'
                      'offsetof(hbpipe,slots),sizeof(hb31_vectors),'
                      'HBPIPE_RAW,HBPIPE_OUTPUT,HBPIPE_CORE0_OUTPUT};\n')
    command([gcc, *C_FLAGS, '-I', SOURCE, '-c', source, '-o', build/'layout.o'], env)
    command([objcopy, '-O', 'binary', '--only-section=.rodata', build/'layout.o', build/'layout.bin'], env)
    values = struct.unpack('<9I', (build/'layout.bin').read_bytes())
    assert values[6:] == (1024, 512, 32)
    return dict(zip(('pipeline_bytes', 'slot_bytes', 'workspace_bytes',
                     'producer_history_bytes', 'slots_offset', 'coefficient_vector_bytes',
                     'raw_block_samples', 'output_block_samples', 'core0_output_samples'), values))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--toolchain', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    tc = args.toolchain if args.toolchain.is_absolute() else ROOT/args.toolchain
    output = args.output if args.output.is_absolute() else ROOT/args.output
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['XTENSA_GNU_CONFIG'] = str(tc/'lib/xtensa_esp32s3.so')
    gcc, objdump, objcopy = [tc/'bin'/('xtensa-esp-elf-'+x) for x in ('gcc', 'objdump', 'objcopy')]
    checks = Checks()
    with tempfile.TemporaryDirectory(prefix='t-halfband-pipeline-') as temp:
        build = Path(temp)
        version = checks.run('target_version', lambda: command([gcc, '--version'], env).splitlines()[0])
        def version_gate():
            assert version and 'esp-14.2.0_20241119' in version and version.endswith('14.2.0'), version
            return True
        checks.run('fixed_GCC14_2_version', version_gate, requires=('target_version',))
        checks.run('target_c_build', lambda: command([gcc, *C_FLAGS, '-c',
            SOURCE/'halfband_pipeline.c', '-o', build/'pipeline.o'], env))
        checks.run('target_asm_build', lambda: command([gcc, '-c', SOURCE/'halfband31.S',
            '-o', build/'kernel.o'], env))
        checks.run('host_arithmetic_build', lambda: command(['gcc', *C_FLAGS, '-shared', '-fPIC',
            SOURCE/'halfband_pipeline.c', SOURCE/'halfband31.c', SOURCE/'halfband31_host.c',
            '-o', build/'host.so']))
        # Timing state-machine tests do not need to repeat arithmetic 40 million
        # times. Only these two leaf functions are replaced; ownership C is exact.
        stub = build/'timing_leaf.c'
        stub.write_text('#include "halfband31.h"\n#include <string.h>\n'
            'void hb31_qacc4(const int16_t*a,const int16_t*b,const int16_t c[17][8],'
            'int16_t out[8],uint32_t shift){(void)a;(void)b;(void)c;(void)shift;'
            'for(unsigned k=0;k<8;++k)out[k]=0;}\n'
            'void hb31_copy_words(void*d,const void*s,size_t n){memcpy(d,s,n*4);}\n')
        checks.run('host_timing_build', lambda: command(['gcc', *C_FLAGS, '-shared', '-fPIC',
            '-I', SOURCE, SOURCE/'halfband_pipeline.c', SOURCE/'halfband31.c', stub,
            '-o', build/'timing.so']))
        c_dis = checks.run('target_c_disassembly', lambda: command([objdump, '-dr', build/'pipeline.o'], env),
                          requires=('target_c_build',))
        asm_dis = checks.run('target_asm_disassembly', lambda: command([objdump, '-dr', build/'kernel.o'], env),
                            requires=('target_asm_build',))
        # Normalize temporary directory names for deterministic saved artifacts.
        c_dis = c_dis.replace(str(build), '<temporary-build>') if c_dis else None
        asm_dis = asm_dis.replace(str(build), '<temporary-build>') if asm_dis else None
        host = checks.run('host_independent_convolution_and_ownership', lambda: host_oracle(build/'host.so'),
                          requires=('host_arithmetic_build',))
        kernel = checks.run('target_kernel_semantics', lambda: check_kernel(decoded(asm_dis, 'hb31_qacc4')),
                            requires=('target_asm_disassembly',))
        hazards = checks.run('target_kernel_hazards', lambda: check_kernel_hazards(decoded(asm_dis, 'hb31_qacc4')),
                             requires=('target_asm_disassembly',))
        counts = checks.run('target_CFG_and_callee_counts', lambda: target_counts(c_dis, asm_dis),
                            requires=('target_c_disassembly', 'target_asm_disassembly'))
        scalar = checks.run('scalar_control_hazard_budget', lambda: scalar_control_gate(counts, c_dis, asm_dis),
                            requires=('target_CFG_and_callee_counts', 'target_kernel_hazards'))
        layout = checks.run('target_ABI_layout', lambda: target_layout(gcc, objcopy, build, env))
        limits = checks.run('per_core_capacity', lambda: capacity(counts),
                           requires=('target_CFG_and_callee_counts', 'target_kernel_hazards', 'scalar_control_hazard_budget'))
        events = checks.run('all_finite_event_scenarios', lambda: event_matrix(build/'timing.so', counts),
                           requires=('target_CFG_and_callee_counts', 'target_kernel_hazards', 'scalar_control_hazard_budget', 'host_timing_build'))
        if events is not None:
            checks.run('finite_event_expectations', lambda: (_ for _ in ()).throw(
                AssertionError(json.dumps(events['assertions']))) if not events['audit_pass'] else True)
        else:
            checks.run('finite_event_expectations', lambda: True, requires=('all_finite_event_scenarios',))
        dis_path = output/'halfband_pipeline.dis'
        checks.run('write_disassembly', lambda: dis_path.write_text((c_dis or '# unavailable\n')+(asm_dis or '# unavailable\n')))
        dis_hash = checks.run('disassembly_hash', lambda: hashlib.sha256(dis_path.read_bytes()).hexdigest(),
                             requires=('write_disassembly',))
        source_files = [SOURCE/x for x in ('halfband_pipeline.c', 'halfband_pipeline.h',
            'halfband31.c', 'halfband31.h', 'halfband31.S', 'halfband31_host.c')]
        source_files += [Path(__file__).resolve(), ROOT/'ci/t_halfband_capacity_audit.py']
        hashes = checks.run('source_hashes', lambda: {repo_path(x): hashlib.sha256(x.read_bytes()).hexdigest() for x in source_files})
        summary = {s: sum(x['status'] == s for x in checks.rows) for s in ('PASS', 'FAIL', 'BLOCKED')}
        result = {'status': 'conditional_two_core_CPU_candidate_not_receiver_pass',
            'audit_status': 'PASS' if not summary['FAIL'] and not summary['BLOCKED'] else 'FAIL',
            'non_fail_fast': True, 'check_summary': summary, 'checks': checks.rows,
            'target_compiler': version, 'c_flags': C_FLAGS,
            'split': {'raw_per_block': RAW, 'input_period_us': 64,
                      'core0_outputs': 32, 'core1_outputs': 480, 'workspace_slots': 2},
            'instruction_model': 'alpha 1.0 or 1.1 cycles/instruction, rounded up once per public C operation; not silicon WCET. Callees are counted once, original hb31_process caller is absent.',
            'host_oracle': host, 'kernel_semantics': kernel, 'kernel_hazards': hazards,
            'scalar_control_hazard_budget': scalar,
            'instructions': counts, 'memory': layout, 'capacity': limits,
            'event_model': events, 'source_hashes_SHA256': hashes,
            'disassembly_SHA256': dis_hash,
            'accepted_same_quality': False, 'target_runtime_executed': False,
            'native_RF_and_SDK_integrated': False, 'hardware_PLL_busy_bound_known': False,
            'FPGA_64_over_63_resampler_implemented_or_sized': False,
            'temporary_binaries_saved': False}
        (output/'results.json').write_text(json.dumps(result, indent=2)+'\n')
        if events:
            (output/'events.json').write_text(json.dumps(events, indent=2)+'\n')
        for row in checks.rows:
            print(f'{row["status"]:7} {row["id"]}'+(': '+row['reason'] if 'reason' in row else ''))
        print(f'Audit {result["audit_status"]}: {summary}; {repo_path(output/"results.json")}')
        return 0 if result['audit_status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())

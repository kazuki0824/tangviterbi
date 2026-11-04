#!/usr/bin/env python3
"""Reconstruction v2: native halfband adapter arithmetic and ownership audit.

This host audit uses the recovered adapter C and the retained two-core pipeline
C with a scalar leaf backend. It checks semantics, not ESP32 execution time.
Every declared check is recorded; an earlier failure does not suppress peers.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from ci.t_halfband_capacity_audit import COEFFICIENTS

SOURCE = ROOT / 'experiments/t_preprocess_capacity'
RAW, WORDS, OUT_BYTES = 1024, 16384, 2048
U64 = (1 << 64) - 1
SOURCE_PATHS = [
    'experiments/t_preprocess_capacity/native_adapter.c',
    'experiments/t_preprocess_capacity/native_adapter.h',
    'experiments/t_preprocess_capacity/halfband_pipeline.c',
    'experiments/t_preprocess_capacity/halfband_pipeline.h',
    'experiments/t_preprocess_capacity/halfband31.c',
    'experiments/t_preprocess_capacity/halfband31.h',
    'experiments/t_preprocess_capacity/halfband31_host.c',
    'tests/t_native_adapter_host.c',
    'ci/t_native_adapter_audit.py',
]


class CollectedCheckError(AssertionError):
    """A failed group retains results for every independent member."""
    def __init__(self, details):
        self.details = details
        super().__init__(f'{len(details["failures"])} independent checks failed')


def collect_independent(items, check):
    failures, completed = [], []
    for item in items:
        try:
            completed.append({'item': item, 'result': check(item)})
        except Exception as exc:
            failures.append({'item': item, 'reason': repr(exc)})
    details = {'executed_count': len(completed)+len(failures),
               'passed_count': len(completed), 'failures': failures,
               'completed': completed}
    if failures:
        raise CollectedCheckError(details)
    return details


def collect_source_hashes(names=SOURCE_PATHS):
    return collect_independent(names, lambda name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest())


class Result(C.Structure):
    _fields_ = [('consumed', C.c_uint), ('copied', C.c_uint),
                ('produced', C.c_uint), ('sequence', C.c_uint32),
                ('first_sample', C.c_uint64)]


def aligned(size):
    owner = C.create_string_buffer(size + 31)
    pointer = (C.addressof(owner) + 15) & ~15
    C.memset(pointer, 0, size)
    return owner, pointer


def sample(n):
    i, q = (73*n + (n >> 3)) & 1023, (131*n + 17) & 1023
    return i | (q << 10) | (((n*317 + 0xa55) & 4095) << 20)


def signed10(word):
    value = word & 1023
    return value - 1024 if value & 512 else value


def oracle(words, shift):
    pairs = [(signed10(word), signed10(word >> 10)) for word in words]
    out = []
    for n in range(0, len(words), 2):
        for component in (0, 1):
            total = sum(coef*pairs[n-t][component]
                        for t, coef in enumerate(COEFFICIENTS) if n >= t)
            out.append(max(-32768, min(32767, total >> shift)))
    return out


def build_library(output):
    command = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               '-fPIC', '-shared', '-fsanitize=undefined',
               '-fno-sanitize-recover=all', '-I'+str(SOURCE),
               '-I'+str(ROOT/'experiments'),
               str(SOURCE/'native_adapter.c'), str(SOURCE/'halfband_pipeline.c'),
               str(SOURCE/'halfband31.c'), str(SOURCE/'halfband31_host.c'),
               str(ROOT/'tests/t_native_adapter_host.c'), '-o', str(output)]
    result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return {'command': command, 'returncode': result.returncode,
            'stdout': result.stdout, 'stderr': result.stderr}


def open_library(path):
    lib = C.CDLL(str(path))
    signatures = {
        'hbpipe_init': ([C.c_void_p, C.c_uint32], C.c_int),
        'hbpipe_size': ([], C.c_size_t),
        'hbpipe_work': ([C.c_void_p], C.c_int),
        'hbpipe_reap': ([C.c_void_p, C.POINTER(C.c_void_p), C.POINTER(C.c_uint32)], C.c_int),
        'hbpipe_status': ([C.c_void_p, C.c_uint], C.c_uint),
        'hbnative_init': ([C.c_void_p, C.c_void_p, C.c_uint32], C.c_int),
        'hbnative_size': ([], C.c_size_t),
        'hbnative_fault': ([C.c_void_p], C.c_uint),
        'host_accept': ([C.c_void_p, C.c_uint, C.c_void_p, C.c_uint, C.c_uint,
                         C.c_uint64, C.c_uint64, C.c_uint64], C.c_int),
        'host_step': ([C.c_void_p, C.c_void_p, C.c_uint, C.c_uint64, C.c_uint64,
                       C.c_uint, C.c_uint, C.POINTER(Result)], C.c_int),
        'host_available': ([C.c_void_p, C.c_uint], C.c_int),
        'host_reclaim': ([C.c_void_p, C.c_uint], C.c_int),
        'host_value': ([C.c_void_p, C.c_uint], C.c_uint64),
        'host_carry': ([C.c_void_p, C.c_uint], C.c_uint32),
        'host_layout': ([C.c_uint], C.c_uint),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(lib, name); fn.argtypes = args; fn.restype = result
    return lib


class Fixture:
    def __init__(self, lib, shift=10, outputs=6):
        self.lib, self.shift, self.clock = lib, shift, 0
        self.pipe_owner, self.pipe = aligned(lib.hbpipe_size())
        self.adapter_owner, self.adapter = aligned(lib.hbnative_size())
        self.banks = [aligned(WORDS*4) for _ in range(3)]
        self.outputs = [aligned(OUT_BYTES+32) for _ in range(outputs)]
        for _, ptr in self.outputs:
            C.memset(ptr, 0xa5, OUT_BYTES+32)
        assert lib.hbpipe_init(self.pipe, shift) == 0
        assert lib.hbnative_init(self.adapter, self.pipe, 1) == 0

    def fill(self, bank, first, words):
        target = (C.c_uint32*WORDS).from_address(self.banks[bank][1])
        for n, value in enumerate(words):
            target[(first+n) & (WORDS-1)] = value

    def accept(self, bank, first, words, first_sample, deadline=10**12):
        self.fill(bank, first, words)
        return self.lib.host_accept(self.adapter, bank, self.banks[bank][1],
                                    first, len(words), first_sample, self.clock, deadline)

    def step(self, output=0, budget=RAW, before=None, after=None, error=0, bound=20000):
        before = self.clock+1 if before is None else before
        after = before if after is None else after
        result = Result()
        pointer = None if output is None else self.outputs[output][1]
        rc = self.lib.host_step(self.adapter, pointer, budget, before, after,
                               error, bound, C.byref(result))
        self.clock = after
        return rc, result

    def finish(self, sequence, expected):
        assert self.lib.hbpipe_work(self.pipe) == 0
        out, seq = C.c_void_p(), C.c_uint32()
        assert self.lib.hbpipe_reap(self.pipe, C.byref(out), C.byref(seq)) == 0
        assert seq.value == sequence and out.value == self.outputs[sequence][1]
        actual = list((C.c_int16*RAW).from_address(out.value))
        assert actual == expected, f'output mismatch sequence={sequence}'
        assert C.string_at(out.value+OUT_BYTES, 32) == b'\xa5'*32

    def value(self, key):
        return self.lib.host_value(self.adapter, key)


def recovered_sources():
    names = ['experiments/t_preprocess_capacity/native_adapter.c',
             'experiments/t_preprocess_integration_probe/tpre_runtime.c',
             'experiments/t_preprocess_integration_probe/tpre_runtime.h']
    def check(name):
        data = (ROOT/name).read_bytes()
        assert data == (ROOT/'reports/s3-t-preprocess-integration/recovered-source'/name).read_bytes(), name
        return hashlib.sha256(data).hexdigest()
    result = collect_independent(names, check)
    return {item['item']: item['result'] for item in result['completed']}


def init_contract(lib):
    f = Fixture(lib)
    variants = [(0, f.pipe, 1), (f.adapter+1, f.pipe, 1),
                (f.adapter, 0, 1), (f.adapter, f.pipe+1, 1),
                (f.adapter, f.pipe, 0), (f.adapter, f.pipe, 65536)]
    def check(index):
        assert lib.hbnative_init(*variants[index]) == 4
    collect_independent(range(len(variants)), check)
    assert lib.host_layout(1) == 16 and lib.host_layout(5) == 4096
    assert lib.host_layout(3) == C.sizeof(Result)
    return {'invalid_init_calls': 6, 'host_adapter_bytes': lib.hbnative_size(),
            'host_pipeline_bytes': lib.hbpipe_size(), 'carry_bytes': 4096,
            'target_layout_is_separately_measured': True}


def stream_case(lib, shift):
    f = Fixture(lib, shift)
    data = [sample(n) for n in range(RAW*4+887)]
    expected = oracle(data[:RAW*4], shift)
    assert f.accept(0, 0, data, 0)
    for sequence in range(4):
        rc, result = f.step(output=sequence)
        assert rc == 0 and (result.consumed, result.copied, result.produced) == (RAW, 0, 1)
        assert result.sequence == sequence and result.first_sample == sequence*RAW
        f.finish(sequence, expected[sequence*RAW:(sequence+1)*RAW])
    rc, result = f.step(output=4)
    assert rc == 0 and result.consumed == 887 and not result.produced
    assert f.value(0) == 0 and f.value(1) == 887
    assert [lib.host_carry(f.adapter, n) for n in range(887)] == data[RAW*4:]
    C.memset(f.banks[0][1], 0x5a, WORDS*4)
    assert f.value(2) == f.value(3) == len(data) and f.value(4) == RAW*4
    before = [lib.host_carry(f.adapter, n) for n in range(887)]
    rc, result = f.step(output=4)
    assert rc == 1 and not any((result.produced, result.consumed, result.copied))
    assert before == [lib.host_carry(f.adapter, n) for n in range(887)]
    return {'shift': shift, 'blocks': 4, 'raw': len(data), 'tail': 887,
            'complex_outputs_compared': 2048, 'tail_padding_or_drop': False}


def all_splits(lib, wrap):
    words = [sample(n) for n in range(RAW)]
    expected = oracle(words, 10)
    def check(split):
        f = Fixture(lib, outputs=1)
        if wrap:
            assert f.accept(0, WORDS-split, words, 0)
        else:
            assert f.accept(0, 0, words[:split], 0)
            assert f.accept(1, 0, words[split:], split)
        rc, result = f.step()
        assert rc == 0 and result.produced == 1 and result.consumed == RAW
        assert result.copied == RAW and f.value(0) == f.value(1) == 0
        for _, p in f.banks:
            C.memset(p, 0x5a, WORDS*4)
        f.finish(0, expected)
    collected = collect_independent(range(1, RAW), check)
    return {'split_positions': RAW-1, 'ring_wrap': wrap,
            'executed_count': collected['executed_count'], 'failures': [],
            'raw_destroyed_before_worker': True, 'complex_outputs_compared': (RAW-1)*512}


def six_segments(lib):
    f = Fixture(lib)
    sizes, cursor = [420, 333, 295], 0
    words = [sample(n) for n in range(sum(sizes))]
    for b, n in enumerate(sizes):
        assert f.accept(b, WORDS-n//2, words[cursor:cursor+n], cursor)
        cursor += n
    rc, result = f.step()
    assert rc == 0 and result.copied == result.consumed == RAW and result.produced == 1
    assert f.value(0) == 1 and lib.host_available(f.adapter, 2) == 0
    C.memset(f.banks[0][1], 0x3c, WORDS*4); C.memset(f.banks[1][1], 0x3c, WORDS*4)
    rc, tail = f.step(output=1)
    assert rc == 0 and tail.consumed == 24 and not tail.produced
    assert f.value(0) == 0 and f.value(1) == 24
    C.memset(f.banks[2][1], 0x3c, WORDS*4)
    f.finish(0, oracle(words[:RAW], 10))
    assert [lib.host_carry(f.adapter, n) for n in range(24)] == words[RAW:]
    return {'banks': 3, 'physical_segments': 6, 'retained_tail': 24,
            'source_destroyed_after_each_release': True}


def backpressure(lib):
    f = Fixture(lib)
    words = [sample(n) for n in range(RAW*3)]
    assert f.accept(0, 0, words, 0)
    for n in range(2):
        assert f.step(output=n)[1].produced == 1
    state = (f.value(0), f.value(1), f.value(3), f.value(4))
    rc, result = f.step(output=2)
    assert rc == 2 and not result.produced and not result.consumed
    assert state == (f.value(0), f.value(1), f.value(3), f.value(4))
    expected = oracle(words, 10)
    f.finish(0, expected[:RAW])
    assert f.step(output=2)[1].produced == 1
    C.memset(f.banks[0][1], 0x5a, WORDS*4)
    f.finish(1, expected[RAW:2*RAW]); f.finish(2, expected[2*RAW:])
    return {'slots': 2, 'blocked_third_producer_preserves_history': True}


def output_lease(lib):
    f = Fixture(lib)
    words = [sample(n) for n in range(RAW)]
    assert f.accept(0, WORDS-513, words, 0)
    rc, result = f.step(output=None)
    assert rc == 3 and result.consumed == result.copied == RAW and not result.produced
    assert f.value(0) == 0 and f.value(1) == RAW
    C.memset(f.banks[0][1], 0x5a, WORDS*4)
    assert [lib.host_carry(f.adapter, n) for n in range(RAW)] == words
    rc, result = f.step(output=None, budget=0)
    assert rc == 3 and not result.consumed and not result.produced
    rc, result = f.step(output=0, budget=0)
    assert rc == 0 and result.produced == 1 and not result.consumed
    f.finish(0, oracle(words, 10))
    return {'full_carry_retained_until_output_reserved': True,
            'all_32_input_bits_preserved': True}


def reinit_live(lib, kind):
    f = Fixture(lib)
    n = 5 if kind == 'tail' else RAW
    assert f.accept(0, 0, [sample(x) for x in range(n)], 0)
    if kind != 'bank':
        f.step()
    before = C.string_at(f.adapter, lib.hbnative_size())
    assert lib.hbnative_init(f.adapter, f.pipe, 2) == 4
    assert before == C.string_at(f.adapter, lib.hbnative_size())
    return {'live': kind, 'reinit_rejected_without_state_change': True}


def reject_accept(lib, kind):
    f = Fixture(lib)
    args = [f.adapter, 0, f.banks[0][1], 0, 10, 0, 0, 100000]
    expected = 1
    if kind == 'bank': args[1] = 3
    elif kind == 'null': args[2] = None
    elif kind == 'unaligned': args[2] += 1
    elif kind == 'first': args[3] = WORDS
    elif kind == 'empty': args[4] = 0
    elif kind == 'count': args[4] = WORDS+1
    elif kind == 'overflow': args[5] = U64; expected = 8
    elif kind == 'sequence': args[5] = 1; expected = 3
    elif kind == 'clock': args[6] = U64; expected = 7
    elif kind == 'deadline': args[7] = 0; expected = 4
    elif kind == 'owned':
        assert lib.host_accept(*args)
        args[5] = 10; expected = 2
    else: raise ValueError(kind)
    assert lib.host_accept(*args) == 0
    assert f.value(6) == expected
    assert f.step()[0] == 5 and f.value(6) == expected
    return {'input': kind, 'fault': expected, 'fault_latched': True}


def step_fault(lib, kind):
    f = Fixture(lib)
    words = [sample(n) for n in range(RAW)]
    deadline = 20001 if kind == 'admission_equal' else 1000000
    assert f.accept(0, 0, words, 0, deadline)
    before, after, error, bound, budget = 1, 1, 0, 20000, RAW
    expected = 1
    if kind == 'budget': budget = RAW+1
    elif kind == 'zero_bound': bound = 0
    elif kind == 'error_bound': error = bound
    elif kind == 'invalid_clock': before = after = U64; expected = 7
    elif kind == 'clock_under_error': error = 2; expected = 7
    elif kind == 'admission_equal': expected = 4
    elif kind == 'post_bound': after = 20002; expected = 6
    elif kind == 'post_clock': after = U64; expected = 7
    else: raise ValueError(kind)
    rc, result = f.step(budget=budget, before=before, after=after, error=error, bound=bound)
    assert rc in (4, 5) and f.value(6) == expected
    if kind.startswith('post_'):
        assert result.produced == 1 and lib.hbpipe_status(f.pipe, 0) == 1
        assert f.value(0) == 0 and f.value(3) == RAW
        C.memset(f.banks[0][1], 0x5a, WORDS*4)
        f.finish(0, oracle(words, 10))
    else:
        assert not result.produced and not result.consumed
        assert f.value(0) == 1 and f.value(3) == 0
    return {'condition': kind, 'fault': expected,
            'published_output_retained': kind.startswith('post_')}


def check_definitions(lib):
    rows = [('host_init_and_layout', lambda: init_contract(lib))]
    rows += [(f'independent_convolution_shift_{shift}', lambda shift=shift: stream_case(lib, shift))
             for shift in (0, 10, 15, 31)]
    rows += [('all_1023_bank_splits', lambda: all_splits(lib, False)),
             ('all_1023_ring_wraps', lambda: all_splits(lib, True)),
             ('three_banks_six_segments', lambda: six_segments(lib)),
             ('two_slot_backpressure', lambda: backpressure(lib)),
             ('output_lease_and_metadata', lambda: output_lease(lib))]
    rows += [(f'reinit_live_{kind}', lambda kind=kind: reinit_live(lib, kind))
             for kind in ('bank', 'tail', 'pipeline')]
    rows += [(f'reject_accept_{kind}', lambda kind=kind: reject_accept(lib, kind)) for kind in
             ('bank', 'null', 'unaligned', 'first', 'empty', 'count', 'overflow',
              'sequence', 'clock', 'deadline', 'owned')]
    rows += [(f'step_fault_{kind}', lambda kind=kind: step_fault(lib, kind)) for kind in
             ('budget', 'zero_bound', 'error_bound', 'invalid_clock', 'clock_under_error',
              'admission_equal', 'post_bound', 'post_clock')]
    return rows


def run_audit():
    checks = []
    def run(name, fn, blocked=None):
        if blocked:
            checks.append({'id': name, 'status': 'BLOCKED', 'reason': blocked}); return None
        try:
            value = fn(); checks.append({'id': name, 'status': 'PASS', 'result': value}); return value
        except Exception as exc:
            row = {'id': name, 'status': 'FAIL', 'reason': repr(exc)}
            if isinstance(exc, CollectedCheckError): row['result'] = exc.details
            checks.append(row); return None
    run('recovered_implementation_bytes_match', recovered_sources)
    with tempfile.TemporaryDirectory(prefix='t-native-v2-') as tmp:
        binary = Path(tmp)/'adapter.so'
        built = run('host_build_UBSan', lambda: build_library(binary))
        lib = run('load_host_library', lambda: open_library(binary),
                  blocked=None if built is not None else 'host build failed')
        # A CDLL handle is not a report datum.
        if lib is not None: checks[-1]['result'] = {'loaded': True}
        for name, fn in check_definitions(lib):
            run(name, fn, blocked=None if lib is not None else 'host library unavailable')
    run('source_hashes_available', collect_source_hashes)
    hashes = {row['item']: row['result'] for row in checks[-1].get('result', {}).get('completed', [])}
    summary = {s: sum(row['status'] == s for row in checks) for s in ('PASS', 'FAIL', 'BLOCKED')}
    return {'schema_version': 2, 'audit_status': 'PASS' if summary['FAIL'] == summary['BLOCKED'] == 0 else 'FAIL',
            'non_fail_fast': True, 'check_summary': summary, 'checks': checks,
            'scope': 'Recovered adapter implementation and retained pipeline C; reconstructed header v2; host scalar FIR leaf and independent direct convolution.',
            'target_timing_measured': False, 'receiver_adopted': False,
            'source_sha256': hashes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/s3-t-preprocess-integration-v2/native/results.json')
    args = parser.parse_args()
    result = run_audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    for row in result['checks']:
        print(row['status'], row['id'], row.get('reason', ''))
    print(json.dumps(result['check_summary']))
    return 0 if result['audit_status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())

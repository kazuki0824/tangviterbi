"""Audit one T ACCX caller: static issue floors, not measured receiver timing.

All planned checks receive PASS, FAIL, or BLOCKED. Host oracle cases execute in
separate processes, so a failed build or even a native crash cannot suppress the
other static checks or the final JSON result. A failed evidence check never
produces the capacity rejection verdict.
"""

import argparse
import ctypes as C
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "experiments/t_preprocess_capacity"
DEFAULT_OUTPUT = ROOT / "reports/s3-t-preprocess-capacity/accx"
BUILD = ROOT / "build/t-accx-capacity"
OPTIMIZATIONS = ("O2", "Os", "O3")
WRAPPER_FLAGS = ("-std=c11", "-Wall", "-Wextra", "-Werror")
HOST_FLAGS = ("-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared")
SOURCE_FILES = (
    "experiments/t_preprocess_capacity/accx_wrapper.c",
    "experiments/t_preprocess_capacity/accx_wrapper.h",
    "experiments/t_preprocess_capacity/accx_host_stub.c",
    "experiments/s3_fir_accx.S",
    "experiments/s3_fir_accx_model.py",
    "ci/t_accx_capacity_audit.py",
)
HOST_CASES = ("random_single", "random_chunks", "extreme1", "extreme2", "rounding_ties")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instructions(dis, symbol):
    body = dis.split("<" + symbol + ">:", 1)[1].split("\n\n", 1)[0]
    rows = []
    for line in body.splitlines():
        match = re.match(r"^\s*([0-9a-f]+):\s+[0-9a-f]+\s+(\S+)\s*(.*)$", line)
        if match and not match[2].startswith("."):
            rows.append((int(match[1], 16), match[2], match[3]))
            if match[2] == "retw.n":
                break
    return rows


def host_oracle_case(library, case):
    """Use direct m*63/32 indexing, independent of wrapper skip recurrence."""
    lib = C.CDLL(str(library))

    class State(C.Structure):
        _fields_ = [("i", C.c_int16 * 64), ("q", C.c_int16 * 64),
                    ("head", C.c_uint32), ("phase", C.c_uint32), ("skip", C.c_uint32)]

    state = State.in_dll(lib, "accx_test_state")
    lib.accx_test_reset.argtypes = [C.POINTER(C.c_int16)]
    lib.accx_t_process.argtypes = [C.POINTER(State), C.POINTER(C.c_uint32), C.c_size_t,
                                  C.POINTER(C.c_int16), C.POINTER(C.c_int16)]
    lib.accx_t_process.restype = C.c_size_t
    rng = random.Random(73)
    if case in ("random_single", "random_chunks"):
        iv = [rng.randrange(-512, 512) for _ in range(4096)]
        qv = [rng.randrange(-512, 512) for _ in range(4096)]
        coeff = [rng.randrange(-32768, 32768) for _ in range(1024)]
    elif case in ("extreme1", "extreme2"):
        iv, qv = [-512] * 2016, [511] * 2016
        coeff = [32767 if case == "extreme1" else -32768] * 1024
    elif case == "rounding_ties":
        iv, qv = [-1, 1, 0, 2, -2] * 403, [1, -1, 0, -2, 2] * 403
        coeff = [256 if k == 0 else 0 for _ in range(32) for k in range(32)]
    else:
        raise ValueError("Unknown host oracle case: " + case)
    rng = random.Random(59)
    words = [((i & 1023) | ((q & 1023) << 10) | (rng.randrange(4096) << 20))
             for i, q in zip(iv, qv)]
    source = (C.c_uint32 * len(words))(*words)
    backing = C.create_string_buffer(2048 + 15)
    coefficient_address = (C.addressof(backing) + 15) & ~15
    coefficient_array = (C.c_int16 * 1024).from_address(coefficient_address)
    coefficient_array[:] = coeff
    lib.accx_test_reset(coefficient_array)
    expected, expected_acc, expected_phases, expected_heads = [], [], [], []
    m = 0
    while (m * 63) // 32 < len(words):
        newest, phase = (m * 63) // 32, (m * 63) % 32
        sums = [sum((data[newest-k] if newest >= k else 0) * coeff[phase*32+k]
                    for k in range(32)) for data in (iv, qv)]
        expected_acc.extend(sums)
        expected.extend(max(-32768, min(32767, (value + 256) // 512)) for value in sums)
        expected_phases.append(phase)
        expected_heads.append((31 - newest) % 32)
        m += 1
    actual, chunks, at = [], [], 0
    while at < len(words):
        n = min(len(words)-at, len(words) if case == "random_single" else rng.randrange(1, 98))
        out = (C.c_int16 * (2*n+2))(*([23130] * (2*n+2)))
        before = bytes(state)
        assert lib.accx_t_process(C.byref(state), source, 0, coefficient_array, out) == 0
        assert bytes(state) == before, "empty call changed state"
        got = lib.accx_t_process(C.byref(state),
            C.cast(C.byref(source, 4*at), C.POINTER(C.c_uint32)), n, coefficient_array, out)
        assert C.c_uint.in_dll(lib, "accx_test_error").value == 0, "host kernel contract violation"
        assert out[2*n] == 23130 and out[2*n+1] == 23130, "output overrun"
        actual.extend(list(out)[:2*got])
        at += n
        chunks.append(n)
        assert list(state.i[:32]) == list(state.i[32:]), "I mirror mismatch"
        assert list(state.q[:32]) == list(state.q[32:]), "Q mirror mismatch"
    calls = C.c_size_t.in_dll(lib, "accx_test_calls").value
    acc = list((C.c_int32 * (16384*2)).in_dll(lib, "accx_test_sums"))[:2*calls]
    phases = list((C.c_uint32 * 16384).in_dll(lib, "accx_test_phases"))[:calls]
    heads = list((C.c_uint32 * 16384).in_dll(lib, "accx_test_heads"))[:calls]
    assert acc == expected_acc, "full precision sums differ"
    assert actual == expected, "final rounded/saturated output differs"
    assert phases == expected_phases and heads == expected_heads, "phase or history differs"
    assert state.head == (-len(words)) % 32
    assert state.phase == (calls*63) % 32
    assert calls == (len(words)*32+62) // 63
    return {"case": case, "input_count": len(words), "output_count": calls,
            "chunks": len(chunks), "distinct_phase_head_pairs": len(set(zip(phases, heads))),
            "full_precision_sums_verified": True, "Q15_trial_rounding_verified": True,
            "aligned_5_vector_read_bounds_verified_in_stub": True,
            "target_runtime_execution": False}


def run(toolchain, output):
    output.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["XTENSA_GNU_CONFIG"] = str(toolchain / "lib/xtensa_esp32s3.so")
    prefix = str(toolchain / "bin/xtensa-esp-elf-")
    checks, checked, costs, source_hashes, dis_hashes = [], {}, [], {}, {}

    def check(name, fn, requires=()):
        blocked = [dependency for dependency in requires if checked[dependency]["status"] != "PASS"]
        if blocked:
            row = {"name": name, "status": "BLOCKED", "passed": False,
                   "reason": "Dependencies did not pass: " + ", ".join(blocked)}
        else:
            try:
                row = {"name": name, "status": "PASS", "passed": True, "detail": fn()}
            except Exception as ex:
                row = {"name": name, "status": "FAIL", "passed": False,
                       "error": type(ex).__name__ + ": " + str(ex)}
        checks.append(row)
        checked[name] = row

    def source_manifest():
        missing = []
        for name in SOURCE_FILES:
            try:
                source_hashes[name] = digest(ROOT / name)
            except OSError as ex:
                missing.append(name + ": " + str(ex))
        if missing:
            raise RuntimeError("; ".join(missing))
        return source_hashes

    check("source_manifest", source_manifest)
    check("target_compiler_identity", lambda: subprocess.check_output(
        [prefix + "gcc", "--version"], env=env, text=True).splitlines()[0])

    def compile_wrapper(opt):
        obj = BUILD / ("accx_wrapper-" + opt + ".o")
        flags = ["-std=c11", "-" + opt, "-Wall", "-Wextra", "-Werror"]
        subprocess.run([prefix + "gcc", *flags, "-c", str(SOURCES / "accx_wrapper.c"),
                        "-o", str(obj)], env=env, check=True, capture_output=True, text=True)
        dis = subprocess.check_output([prefix + "objdump", "-dr", str(obj)], env=env, text=True)
        dis_path = output / ("accx_wrapper-" + opt + ".dis")
        dis_path.write_text(dis.replace(str(obj), obj.name))
        dis_hashes[dis_path.name] = digest(dis_path)
        return {"compiler_flags": flags, "object_sha256": digest(obj),
                "disassembly": dis_path.name, "disassembly_sha256": dis_hashes[dis_path.name]}

    for opt in OPTIMIZATIONS:
        check("target_compile_" + opt, lambda opt=opt: compile_wrapper(opt), ("target_compiler_identity",))

    def compile_kernel():
        obj = BUILD / "accx_kernel.o"
        subprocess.run([prefix + "gcc", "-c", str(ROOT / "experiments/s3_fir_accx.S"),
                        "-o", str(obj)], env=env, check=True, capture_output=True, text=True)
        dis = subprocess.check_output([prefix + "objdump", "-d", str(obj)], env=env, text=True)
        path = output / "accx_kernel.dis"
        path.write_text(dis.replace(str(obj), obj.name))
        dis_hashes[path.name] = digest(path)
        rows = instructions(dis, "s3_fir_accx_32")
        assert len(rows) == 29, len(rows)
        mac_count = sum("vmulas" in op for _, op, _ in rows)
        assert mac_count == 8, mac_count
        return {"compiler_flags": ["-c"], "instructions": len(rows), "MAC_instructions": mac_count,
                "object_sha256": digest(obj), "disassembly": path.name,
                "disassembly_sha256": dis_hashes[path.name]}

    check("target_kernel_29_instructions", compile_kernel, ("target_compiler_identity",))

    # These finite ranges describe the actual three saved compiler schedules.
    # A changed compiler schedule must fail this review instead of silently using
    # the old count. Address selection is validated against opcode multisets.
    ranges = {"O2": [(0x35, 0x66), (0x69, 0xa9), (0xad, 0xad), (0xaf, 0xb6)],
              "Os": [(0x29, 0x4e), (0x51, 0xa1), (0xa4, 0xa4), (0xa6, 0xad)],
              "O3": [(0x36, 0x67), (0x6a, 0xae), (0xb4, 0xbd)]}
    expected = {"O2": [20, 25, 1, 4], "Os": [15, 32, 1, 4], "O3": [20, 27, 5]}
    q15_addresses = {
        "O2": [0x70, 0x72, 0x77, 0x7a, 0x7d, 0x80, 0x83, 0x86, 0x8f, 0x92, 0x95, 0x9a],
        "Os": [0x66, 0x6b, 0x6e, 0x76, 0x79, 0x7c, 0x7f, 0x83, 0x86, 0x89, 0x8c, 0x8f],
        "O3": [0x71, 0x73, 0x78, 0x7b, 0x7e, 0x81, 0x84, 0x87, 0x8f, 0x92, 0x95, 0x98]}

    def audit_paths(opt):
        rows = instructions((output / ("accx_wrapper-" + opt + ".dis")).read_text(), "accx_t_process")
        groups = [[row for row in rows if lo <= row[0] <= hi] for lo, hi in ranges[opt]]
        counts = list(map(len, groups))
        assert counts == expected[opt], counts
        assert sum(op == "s16i" for _, op, _ in groups[0]) == 4
        assert groups[0][-1][1] == "bnez"
        assert sum(op == "call8" for _, op, _ in groups[1]) == 1
        assert not any(op in ("quou", "quos", "remu", "rems") for _, op, _ in rows)
        chosen = [row for row in rows if row[0] in q15_addresses[opt]]
        assert len(chosen) == 12
        for op in ("l32i.n", "addmi", "srai", "min", "max", "s16i"):
            assert sum(row[1] == op for row in chosen) == 2, (op, chosen)
        common, output_path, skip, *tail = counts
        # Exactly 32 output paths + 31 skip paths per 63 inputs. Last input is
        # skipped and its taken exit branch avoids one back jump. Prologue and
        # epilogue are excluded, making this a lower bound even for 63-word calls.
        wrapper = common*63 + output_path*32 + skip*31 + (tail[0]*63 if tail else 0) - 1
        kernel = checked["target_kernel_29_instructions"]["detail"]["instructions"]
        no_q15 = common*16 + (1+kernel)*(512/63)
        mandatory = common*16 + (1+kernel+12)*(512/63)
        assert no_q15 > 480 and mandatory > 480
        row = {"optimization": opt,
            "ranges_hex": [[hex(x), hex(y)] for x, y in ranges[opt]],
            "path_segment_instruction_counts": counts,
            "mandatory_input_instructions": common,
            "caller_call_instructions_per_output": 1,
            "kernel_instructions_per_output": kernel,
            "mandatory_Q15_instructions_per_output": 12,
            "input_call_kernel_only_issue_floor_Mcycles_s": no_q15,
            "mandatory_subset_issue_floor_Mcycles_s": mandatory,
            "wrapper_loop_instructions_per_63_inputs": wrapper,
            "kernel_instructions_per_32_outputs": kernel*32,
            "combined_loop_issue_floor_Mcycles_s": (wrapper+kernel*32)*16/63,
            "ideal_two_core_capacity_Mcycles_s": 480,
            "fits_ideal_two_core_capacity": False, "runtime_measured": False}
        costs.append(row)
        return row

    for opt in OPTIMIZATIONS:
        check("target_paths_and_mandatory_subset_" + opt, lambda opt=opt: audit_paths(opt),
              ("target_compile_" + opt, "target_kernel_29_instructions"))

    def compile_host():
        library = BUILD / "accx_host.so"
        subprocess.run(["gcc", *HOST_FLAGS, str(SOURCES / "accx_wrapper.c"),
                        str(SOURCES / "accx_host_stub.c"), "-o", str(library)],
                       check=True, capture_output=True, text=True)
        return {"compiler_flags": list(HOST_FLAGS), "library_sha256": digest(library),
                "scope": "Host scalar kernel stub; never substituted for target timing"}

    check("host_build", compile_host)

    def oracle_subprocess(case):
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()),
            "--_host-case", case, "--_host-library", str(BUILD / "accx_host.so")],
            capture_output=True, text=True)
        if completed.returncode:
            raise RuntimeError("Oracle subprocess exit " + str(completed.returncode) + ": " +
                               (completed.stdout + completed.stderr).strip())
        return json.loads(completed.stdout)

    for case in HOST_CASES:
        check("host_oracle_" + case, lambda case=case: oracle_subprocess(case), ("host_build",))

    def kernel_model_test():
        spec = importlib.util.spec_from_file_location("accx_semantics", ROOT / "experiments/s3_fir_accx_model.py")
        model = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(model)
        code = model.instructions((output / "accx_kernel.dis").read_text(), "s3_fir_accx_32")
        rng, tested = random.Random(87), 0
        for ia in range(0, 16, 2):
            for qa in range(0, 16, 2):
                iv = [rng.randrange(-512, 512) for _ in range(32)]
                qv = [rng.randrange(-512, 512) for _ in range(32)]
                coeff = [rng.randrange(-32768, 32768) for _ in range(32)]
                result, reads = model.execute(code, iv, qv, coeff, ia, qa)
                assert result == (sum(x*y for x, y in zip(iv, coeff)), sum(x*y for x, y in zip(qv, coeff)))
                assert len(reads) == 14
                tested += 1
        return {"alignments": tested, "target_runtime_execution": False}

    check("existing_kernel_semantic_model_all_halfword_alignments", kernel_model_test,
          ("target_kernel_29_instructions",))
    success = all(check["passed"] for check in checks)
    result = {"scope": __doc__, "compiler": checked["target_compiler_identity"].get("detail"),
        "source_sha256": source_hashes, "disassembly_sha256": dis_hashes,
        "input_Mcomplex_samples_s": 16, "output_Mcomplex_samples_s": 512/63,
        "assumptions": [
            "At most one CPU instruction can issue per cycle; every instruction is optimistically allowed one cycle.",
            "Both CPU cores run at 240 MHz with perfect division of work, giving 480 Mcycles/s aggregate capacity.",
            "Native signed10 I/Q input, L/M=32/63, 32 signed16 taps per phase, zero initial history.",
            "PIE context is exclusively available; RF, DMA, RTOS, cache, stalls and contention cost zero.",
            "Q15 trial: coefficient format Q15, round (acc+256)>>9, saturate signed16. Real receiver contract not validated.",
        ],
        "checks": checks, "costs": costs, "all_checks_passed": success,
        "status": "REJECT_THIS_ACCX_WRAPPER" if success else "EVIDENCE_CHECK_FAILED",
        "verdict": "NO for this compiled mirrored-history C wrapper plus existing ACCX kernel" if success else None,
        "target_runtime_executed": False, "universal_ACCX_or_T_impossibility_proved": False,
        "limitations": [
            "Instruction issue floors are not measured target WCET.",
            "FIR coefficient response and deployed receiver Q15 rounding contract not validated.",
            "No target RF/RTOS/DMA integration, PIE context management or two-core schedule.",
            "Even the input/call/kernel subset rejects all three objects with Q15 work treated as free.",
            "Other caller layouts, block/history methods, fused assembly or another FIR algorithm remain separate candidates.",
        ]}
    (output / "accx-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "checks": len(checks),
                      "failed": [row["name"] for row in checks if row["status"] == "FAIL"],
                      "blocked": [row["name"] for row in checks if row["status"] == "BLOCKED"]}))
    return 0 if success else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, help="Espressif Xtensa toolchain directory (required for audit)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--_host-case", choices=HOST_CASES, help=argparse.SUPPRESS)
    parser.add_argument("--_host-library", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args._host_case:
        try:
            print(json.dumps(host_oracle_case(args._host_library, args._host_case)))
            return 0
        except Exception as ex:
            print(json.dumps({"error": type(ex).__name__ + ": " + str(ex)}))
            return 1
    if not args.toolchain:
        parser.error("--toolchain is required; target evidence is rebuilt instead of trusting stale artifacts")
    return run(args.toolchain.resolve(), args.output.resolve())


if __name__ == "__main__":
    raise SystemExit(main())

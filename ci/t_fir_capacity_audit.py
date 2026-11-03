"""Audit the existing T QACC preparation implementation, not all T filters.

The rejection uses only mandatory output writes and the compiled scalar store
width. All other work is free in this necessary-capacity check. No target timing
or receiver-quality success is inferred from host tests or instruction counts.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "experiments/s3_fir_qacc_prepare.c"
HEADER = "experiments/s3_fir_qacc_prepare.h"
SOURCE_REVISION = "1fe8e006a33e146b358d244f0bade5908a4b258d"
REVIEWED_HASHES = {
    SOURCE: "4dfc8013913e2c8ea9616e7ec6ff144a56a59443922930198f9eddfeb004ddfe",
    HEADER: "144d075cdb8faa9e32e71a5f2a39632bafddee4bd8d4c8b46d6d6c9f59c90690",
    "reports/s3-fft-target-bound/core-isa.h": "7019cdf8369feda20f243f11ae5418bde0ecf99cb1c639d1ef4777957a4d800f",
}
REVIEWED_DISASSEMBLIES = {
    "O2": "6cf6a70be79c4b84e5a106ead7c30fc7083350dd9916946eba1e18455ec04dfc",
    "Os": "0185de30c7ea5fef1b5cba2ec229ab9318ecb1705b9ffe5d35b8ef5211c49822",
    "O3": "6f19eb3e32f76c25095d274c09f8de69fa1fa8cebf926c826bba9a3412d200e9",
}
STORE_WIDTHS = {"s8i": 1, "s16i": 2, "s32i": 4, "s32i.n": 4}
MATH_HELPERS = {"__udivdi3", "__umoddi3"}
FLAGS = ("O2", "Os", "O3")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect_disassembly(text):
    """Reject unfamiliar stores/callees rather than assuming they are scalar."""
    marker = "<s3_fir_qacc_prepare>:"
    present = marker in text
    body = text.split(marker, 1)[-1]
    body = re.split(r"\n[0-9a-f]+ <[^>]+>:", body, maxsplit=1)[0]
    instructions = []
    for line in body.splitlines():
        match = re.match(r"\s*([0-9a-f]+):\s+[0-9a-f]+\s+(\S+)(?:\s+(.*))?$", line)
        if match:
            instructions.append((match[1], match[2], match[3] or ""))
    opcodes = [row[1] for row in instructions]
    external = sorted(set(re.findall(r"R_XTENSA_SLOT0_OP\s+([^\s.][^\s]*)", body)))
    unknown_calls = sorted(set(external) - MATH_HELPERS)
    suspicious = sorted(set(op for op in opcodes if (
        op.startswith("ee.") or op.startswith("s32c") or op.startswith("ssi")
        or op.startswith("ssx") or op.startswith("callx")
        or (op.startswith(("s8i", "s16i", "s32i")) and op not in STORE_WIDTHS)
    )))
    widths = [STORE_WIDTHS[op] for op in opcodes if op in STORE_WIDTHS]
    call_count = sum(op.startswith("call") for op in opcodes)
    reloc_call_count = len(re.findall(r"R_XTENSA_SLOT0_OP\s+__(?:udiv|umod)di3\b", body))
    return {
        "function_present": present,
        "instruction_count_static_not_dynamic": len(instructions),
        "store_sites": [{"address": a, "opcode": op, "operands": args}
                        for a, op, args in instructions if op in STORE_WIDTHS],
        "maximum_scalar_store_bytes": max(widths, default=0),
        "external_helpers": external,
        "unknown_callees": unknown_calls,
        "unsupported_memory_or_indirect_ops": suspicious,
        "all_calls_accounted_for": call_count == reloc_call_count,
        "scalar_store_proof_supported": bool(present and widths and not suspicious
                                               and not unknown_calls
                                               and call_count == reloc_call_count),
    }


def capacity_floor(maximum_store_bytes):
    """Count compulsory writes; omit even the QACC computation and RF service."""
    if maximum_store_bytes <= 0:
        raise ValueError("A positive audited store width is required")
    taps, outputs, components, arrays, component_bytes = 32, 4, 2, 2, 2
    output_rate = 16_000_000 * 32 / 63
    bytes_per_batch = taps * outputs * components * arrays * component_bytes
    stores_per_batch = math.ceil(bytes_per_batch / maximum_store_bytes)
    required = stores_per_batch * output_rate / outputs
    return {
        "input_complex_samples_per_second": 16_000_000,
        "output_complex_samples_per_second": output_rate,
        "outputs_per_batch": outputs,
        "batches_per_second": output_rate / outputs,
        "preparation_output_bytes_per_batch": bytes_per_batch,
        "optimistic_store_width_bytes": maximum_store_bytes,
        "minimum_store_instructions_per_batch": stores_per_batch,
        "minimum_store_Mcycles_per_second": required / 1_000_000,
        "two_core_capacity_Mcycles_per_second": 480,
        "minimum_aggregate_utilization_percent": required / 4_800_000,
        "exceeds_two_core_capacity": required > 480_000_000,
    }


def run(output, toolchain=None):
    output.mkdir(parents=True, exist_ok=True)
    checks, variants = [], []

    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    sources = {}
    for path, expected in REVIEWED_HASHES.items():
        try:
            actual = digest((ROOT / path).read_bytes())
        except OSError as error:
            actual = "UNAVAILABLE: " + str(error)
        sources[path] = actual
        check("reviewed_source:" + path, actual == expected, actual)
    compiler = "Espressif GCC 14.2.0 esp-14.2.0_20241119 (saved disassembly)"
    env = os.environ.copy()
    if toolchain:
        toolchain = toolchain.resolve()
        env["XTENSA_GNU_CONFIG"] = str(toolchain / "lib/xtensa_esp32s3.so")
        prefix = toolchain / "bin/xtensa-esp-elf-"
        try:
            compiler = subprocess.check_output([str(prefix) + "gcc", "--version"], env=env, text=True).splitlines()[0]
            check("compiler_available", True, compiler)
        except (OSError, subprocess.CalledProcessError) as error:
            compiler = "UNAVAILABLE: " + str(error)
            check("compiler_available", False, compiler)
    for flag in FLAGS:
        dis_path = output / ("prepare-" + flag + ".dis")
        if toolchain:
            build = ROOT / "build/t-preprocess-capacity/qacc"
            build.mkdir(parents=True, exist_ok=True)
            obj = build / ("prepare-" + flag + ".o")
            command = [str(prefix) + "gcc", "-std=c11", "-" + flag,
                       "-Wall", "-Wextra", "-Werror", "-c", str(ROOT / SOURCE), "-o", str(obj)]
            try:
                completed = subprocess.run(command, env=env, capture_output=True, text=True)
            except OSError as error:
                check(flag + ":compile", False, str(error))
                variants.append({"optimization": flag, "status": "compile_unavailable"})
                continue
            check(flag + ":compile", completed.returncode == 0, completed.stderr.strip())
            if completed.returncode:
                variants.append({"optimization": flag, "status": "compile_failed"})
                continue
            try:
                dis = subprocess.check_output([str(prefix) + "objdump", "-dr", str(obj)], env=env, text=True)
            except (OSError, subprocess.CalledProcessError) as error:
                check(flag + ":disassemble", False, str(error))
                variants.append({"optimization": flag, "status": "disassemble_failed"})
                continue
            dis_path.write_text(dis.replace(str(obj), obj.name))
        if not dis_path.exists():
            check(flag + ":disassembly_available", False, str(dis_path))
            variants.append({"optimization": flag, "status": "missing_disassembly"})
            continue
        data = dis_path.read_bytes()
        reviewed_disassembly = digest(data) == REVIEWED_DISASSEMBLIES[flag]
        check(flag + ":reviewed_disassembly", reviewed_disassembly, digest(data))
        analysis = inspect_disassembly(data.decode())
        check(flag + ":scalar_store_proof", analysis["scalar_store_proof_supported"], analysis)
        row = {"optimization": flag, "disassembly": dis_path.name,
               "disassembly_sha256": digest(data), "analysis": analysis}
        if reviewed_disassembly and analysis["scalar_store_proof_supported"]:
            row["necessary_capacity"] = capacity_floor(analysis["maximum_scalar_store_bytes"])
            check(flag + ":capacity_rejection", row["necessary_capacity"]["exceeds_two_core_capacity"],
                  row["necessary_capacity"])
        else:
            check(flag + ":capacity_rejection", False,
                  "BLOCKED: reviewed instruction evidence did not pass")
        variants.append(row)
    success = all(item["passed"] for item in checks) and len(variants) == len(FLAGS)
    result = {
        "scope": "Existing reference scalar prepare C plus QACC T32, not every T FIR implementation",
        "input_revision": SOURCE_REVISION,
        "compiler": compiler,
        "source_sha256": sources,
        "assumptions": [
            "Call arguments: up=32, down=63, taps=32; four output lanes; distinct adequately sized arrays",
            "Both output arrays are materialized on every invocation as implemented by the reviewed C",
            "Each CPU is 240 MHz and issues at most one instruction per cycle (ESP32-S3 TRM section 1.7); two cores are assumed perfectly balanced",
            "The pinned target ISA header has one load/store unit; scalar store width is checked in the compiled instructions",
            "Every scalar store is allowed to write the maximum width observed, even where actual stores are 16-bit",
            "All reads, arithmetic, division, QACC, caller, RF, RTOS, waits and contention cost zero",
        ],
        "variants": variants,
        "checks": checks,
        "status": "REJECT_EXISTING_SCALAR_PREPARE" if success else "EVIDENCE_CHECK_FAILED",
        "target_runtime_executed": False,
        "all_T_preprocessing_excluded": False,
    }
    (output / "qacc-preparation-capacity.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "checks": len(checks),
                      "failed": [item["name"] for item in checks if not item["passed"]]}, ensure_ascii=False))
    return 0 if success else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, help="Compile all three variants; omit to check saved disassembly")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/s3-t-preprocess-capacity")
    args = parser.parse_args()
    return run(args.output.resolve(), args.toolchain)


if __name__ == "__main__":
    raise SystemExit(main())

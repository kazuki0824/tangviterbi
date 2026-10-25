"""Static K7 RTL regression guards, including mutation tests for prior bug.

These checks supplement, rather than replace, independent Icarus decoding.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RTL_NAMES = ("three_context_k7.sv", "three_context_k7_window.sv",
             "three_context_k7_coole_scheduled.sv", "three_context_k7_bm_staged.sv")
TRACER = "three_context_k7_coole_scheduled.sv"


def without_comments(source):
    # Support both line and block comments; RTL files here use no string literals
    # containing comment delimiters outside initial $fatal messages.
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)


def check_trace_start(source):
    code = without_comments(source)
    m = re.search(r"\bif\s*\(\s*start_trace\s*\)\s*begin\b(.*?)\bend\b",code,re.S)
    if not m:
        raise ValueError("missing start_trace begin/end block")
    body = m.group(1)
    for field in ("read_ptr","state","walk"):
        pattern = rf"\b{field}\s*\[\s*context_id\s*\]\s*<=\s*(?:0|wr_ptr\[context_id\]\s*-\s*4)\s*;"
        if not re.search(pattern,body):
            raise ValueError(f"missing active {field} initialization in start_trace")
    if not re.search(r"\btracing\s*\[\s*context_id\s*\]\s*<=\s*1\s*;",body):
        raise ValueError("traceback start does not activate tracing")


def check_ports(source):
    code = without_comments(source)
    for port in ("input  wire [7:0]  soft0", "input  wire [7:0]  soft1",
                 "input wire [1:0] erasure", "input wire [1:0] slot_context"):
        if port not in code:
            raise ValueError(f"missing project-preserving input: {port}")
    if "if (METRIC_W != 13 || TRACEBACK != 64)" not in code:
        raise ValueError("metric/traceback safety guard removed")


class TestK7StaticGuards(unittest.TestCase):
    def test_active_traceback_initializations(self):
        code = (ROOT / "rtl" / TRACER).read_text()
        check_trace_start(code)

    def test_mutation_line_comment_must_fail(self):
        source = (ROOT / "rtl" / TRACER).read_text()
        needle = "read_ptr[context_id] <= wr_ptr[context_id] - 4;"
        self.assertEqual(source.count(needle),1)
        mutated = source.replace(
            needle+"\n                state[context_id] <= 0;\n                walk[context_id] <= 0;",
            needle+" // state[context_id] <= 0; walk[context_id] <= 0;")
        self.assertNotEqual(mutated,source,"mutation test was not applied")
        with self.assertRaisesRegex(ValueError,"active state"):
            check_trace_start(mutated)

    def test_mutation_walk_reset_removed_must_fail(self):
        source = (ROOT / "rtl" / TRACER).read_text()
        needle = "                walk[context_id] <= 0;"
        self.assertEqual(source.count(needle),1)
        with self.assertRaisesRegex(ValueError,"active walk"):
            check_trace_start(source.replace(needle,""))

    def test_candidate_interfaces(self):
        for name in RTL_NAMES:
            with self.subTest(name=name):
                check_ports((ROOT/"rtl"/name).read_text())

if __name__ == "__main__":
    unittest.main()

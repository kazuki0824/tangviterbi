"""Run real pinned TLSF; distinguish projection success from boot evidence."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ci'))
from s3_tlsf32_replay import run, prepare_sources

class StartupReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all(importlib.util.find_spec(m) for m in ('unicorn', 'elftools')):
            raise unittest.SkipTest('32-bit allocator replay requires unicorn and pyelftools; see reports/s3-startup-order/README.md')
        cls.directory = tempfile.TemporaryDirectory()
        source = os.environ.get('TLSF_SOURCE')
        cls.result = run(Path(cls.directory.name) / 'result.json', Path(source) if source else None)
        cls.traces = {t['name']: t for t in cls.result['traces']}
        cls.placement = run(Path(cls.directory.name) / 'placement.json', Path(source) if source else None,
                            ('n16r8-late-stacks', 'n16r8-late-stacks-heap-flash'),
                            ROOT / 'reports/s3-startup-order/sdk')

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_all_independent_scenarios_run_despite_failures(self):
        self.assertEqual(len(self.traces), 16)
        self.assertEqual(sum(t['projected_trace_pass'] for t in self.traces.values()), 6)

    def test_late_stack_capacity_pass_still_fails_main_contiguous_allocation(self):
        for records in (0, 1):
            with self.subTest(records=records):
                t = self.traces[f'n16r8-late-stacks-main8192-records{records}']
                last = t['events'][-1]
                self.assertEqual(last['name'], 'main_stack')
                self.assertIsNone(last['heap'])
                self.assertGreater(sum(last['largest_free_blocks']), last['bytes'])
                self.assertLess(max(last['largest_free_blocks']), last['bytes'])

    def test_real_tlsf_selects_diram_before_rtc(self):
        events = self.traces['n16r8-late-stacks-main8192-records1']['events']
        by_name = {e['name']: e for e in events}
        self.assertEqual(by_name['ipc0_stack']['heap'], 1)
        self.assertEqual(by_name['timer_stack']['heap'], 0)
        self.assertEqual(by_name['timer_TCB']['largest_free_blocks'], [6664, 1880, 7780])

    def test_smaller_main_is_only_a_sensitivity_case(self):
        for size in (6144, 4096, 3584):
            with self.subTest(size=size):
                t = self.traces[f'n16r8-late-stacks-main{size}-records1']
                self.assertTrue(t['projected_trace_pass'])
                self.assertEqual(len(t['events']), 13)
        self.assertFalse(self.result['hardware_boot_executed'])
        self.assertFalse(self.result['receiver_adopted'])
        self.assertIn('unbuilt sensitivity', self.result['conclusion_scope'])

    def test_real_flash_placement_retains_main_stack_and_passes_projection(self):
        trace = next(t for t in self.placement['traces']
                     if t['name'] == 'n16r8-late-stacks-heap-flash-main8192-records1')
        self.assertTrue(trace['projected_trace_pass'])
        self.assertEqual(next(e['bytes'] for e in trace['events'] if e['name'] == 'main_stack'), 8704)
        source = ROOT / 'reports/s3-startup-order/sdk'
        before = json.loads((source / 'n16r8-late-stacks/result.json').read_text())
        after = json.loads((source / 'n16r8-late-stacks-heap-flash/result.json').read_text())
        self.assertEqual(before['sizes'], after['sizes'])
        self.assertEqual(after['startup']['main_stack_bytes'], before['startup']['main_stack_bytes'])
        self.assertEqual(sum(int(b, 16) - int(a, 16) for a, b in after['payload_regions']), 131072)
        self.assertFalse(self.placement['hardware_boot_executed'])

    def test_tampered_allocator_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'tlsf.c').write_text('corrupted')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                prepare_sources(Path(d))

if __name__ == '__main__':
    unittest.main()

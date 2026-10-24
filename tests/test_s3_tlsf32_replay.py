"""Run real pinned TLSF; distinguish projection success from boot evidence."""
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
        cls.directory = tempfile.TemporaryDirectory()
        source = os.environ.get('TLSF_SOURCE')
        cls.result = run(Path(cls.directory.name) / 'result.json', Path(source) if source else None)
        cls.traces = {t['name']: t for t in cls.result['traces']}

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

    def test_tampered_allocator_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'tlsf.c').write_text('corrupted')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                prepare_sources(Path(d))

if __name__ == '__main__':
    unittest.main()

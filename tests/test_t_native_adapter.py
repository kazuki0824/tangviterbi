"""Executable ownership/oracle regressions for the reconstructed native adapter."""
import tempfile
import unittest
from pathlib import Path
from ci import t_native_adapter_audit as audit


class NativeAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / 'native.so'
        audit.build_library(path)
        cls.lib = audit.open_library(path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_recovered_source_bytes(self):
        audit.recovered_sources()

    def test_all_split_points_against_independent_convolution(self):
        for wrap in (False, True):
            with self.subTest(wrap=wrap):
                audit.all_splits(self.lib, wrap)

    def test_stream_shifts_and_unpadded_tail(self):
        for shift in (0, 10, 15, 31):
            with self.subTest(shift=shift):
                audit.stream_case(self.lib, shift)

    def test_output_and_source_ownership(self):
        for name in ('six_segments', 'backpressure', 'output_lease'):
            with self.subTest(case=name):
                getattr(audit, name)(self.lib)

    def test_faults_and_reinitialization(self):
        for name, check in audit.check_definitions(self.lib):
            if name.startswith(('reject_', 'step_fault_', 'reinit_')):
                with self.subTest(case=name):
                    check()

    def test_early_independent_failure_does_not_skip_later_members(self):
        visited = []
        def check(item):
            visited.append(item)
            if item == 1:
                raise AssertionError('injected first-member failure')
            return item
        with self.assertRaises(audit.CollectedCheckError) as raised:
            audit.collect_independent(range(1, 1024), check)
        self.assertEqual(visited, list(range(1, 1024)))
        self.assertEqual(raised.exception.details['executed_count'], 1023)
        self.assertEqual(raised.exception.details['passed_count'], 1022)

    def test_missing_source_does_not_suppress_later_hashes(self):
        with self.assertRaises(audit.CollectedCheckError) as raised:
            audit.collect_source_hashes(['missing-native-check-file.c',
                                        'experiments/t_preprocess_capacity/native_adapter.c'])
        detail = raised.exception.details
        self.assertEqual(detail['executed_count'], 2)
        self.assertEqual(detail['passed_count'], 1)
        self.assertEqual(detail['completed'][0]['item'],
                         'experiments/t_preprocess_capacity/native_adapter.c')


if __name__ == '__main__':
    unittest.main()

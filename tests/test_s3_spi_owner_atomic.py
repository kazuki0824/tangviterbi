import unittest
from experiments.s3_spi_owner_atomic import OPS, explore, report


class OwnerAtomicTest(unittest.TestCase):
    def test_all_subsequences_and_initial_bits(self):
        result = report()
        self.assertEqual(len(result['rows']), 64)
        self.assertEqual(result['max_failed_attempts'], 4)
        self.assertEqual(result['max_total_attempts'], 5)
        self.assertIsNone(result['elapsed_upper_cycles'])
        self.assertFalse(result['bound_is_tight_for_runtime'])
        self.assertFalse(result['receiver_adopted'])

    def test_explicit_envelope_witness(self):
        # Independent direct replay: one foreign change before each attempt.
        value = expected = 3
        for op in OPS:
            value = value | op[2] if op[1] == 'or' else value & op[2]
            self.assertNotEqual(value, expected)
            expected = value
        self.assertEqual(value, expected)  # next CAS succeeds
        result = explore(3, OPS)
        self.assertEqual(result['witness'].count('owner CAS failure'), 4)

    def test_no_change_does_not_fail_compare_value_cas(self):
        self.assertEqual(explore(0, (OPS[0], OPS[2], OPS[3]))['max_failed_attempts'], 0)
        self.assertEqual(explore(3, ())['max_failed_attempts'], 0)


if __name__ == '__main__':
    unittest.main()

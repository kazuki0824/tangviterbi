"""Acceptance-policy and independently calculated conservation checks."""
import importlib.util
import math
from fractions import Fraction
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('audit', Path(__file__).parents[1] / 'experiments/control_only_estimate.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class ControlOnlyEstimateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = audit.rows('9k')
        cls.by_id = {r['id']: r for r in cls.rows}
        cls.sets = audit.port_sets()

    def test_every_graph_assignment_and_only_prefix_cuts(self):
        self.assertEqual(len(self.rows), 320)
        for st, count in [('T', 9), ('S', 7)]:
            selected = [r for r in self.rows if r['standard'] == st and r['command_only_return_compatible']]
            self.assertEqual(len(selected), count)
            actual = {tuple(r['owners'][x] for x in audit.ORDER[st]) for r in selected}
            expected = {('SoC',) * i + ('FPGA',) * (count - 1 - i) for i in range(count)}
            self.assertEqual(actual, expected)

    def test_reproduce_old_CPU_except_identified_duplicate(self):
        for r in self.rows:
            with self.subTest(row=r['id']):
                self.assertLess(max(map(abs, r['CPU_model_recheck_error_Mcycles_s'])), 1e-8)
        self.assertAlmostEqual(self.by_id['S3-T-007']['removed_duplicate_reorder_Mcycles_s'][0], 46.79172679172679)
        self.assertGreater(self.by_id['S3-T-007']['CPU_before_driver_percent'][0], 100)

    def test_rates_from_independent_rational_expressions(self):
        useful_rate = Fraction(512_000_000, 63)
        period = Fraction(8192, 1) / useful_rate * Fraction(33, 32)
        coded_bits = Fraction(4992 * 6 * 7, 8) / period
        ts = coded_bits * Fraction(188, 204)
        self.assertAlmostEqual(audit.T_RS, float(coded_bits / (204 * 8)))
        self.assertAlmostEqual(audit.T_RS * 188 * 8, float(ts))
        self.assertAlmostEqual(1e6 / audit.S_RS, float(Fraction(203 * 8 * 1_000_000, 2 * 28_860_000)))

    def test_payload_conservation_and_no_return_data(self):
        for r in self.rows:
            with self.subTest(row=r['id']):
                self.assertAlmostEqual(r['forward_MBps'] + r['reverse_payload_MBps'], sum(f['MBps'] for f in r['flows']))
                if r['reverse_payload_MBps']:
                    self.assertIn('FORBIDDEN_FPGA_TO_SOC_PAYLOAD', r['reasons'])
        self.assertEqual(self.by_id['S3-S-000']['forward_MBps'], 40 * 20 / 8)

    def test_peripheral_exclusivity_and_shared_DMA_limit(self):
        self.assertEqual(len(audit.ports()), 18)
        for group in self.sets:
            self.assertEqual(len(group), len({p['group'] for p in group}))
            self.assertLessEqual(sum(p['dma_tx'] for p in group), 5)
            self.assertLessEqual(sum(p['dma_rx'] for p in group), 5)
            self.assertLessEqual(sum(p['pins'] for p in group) + 1, 30)

    def test_all_bandwidth_witnesses_pay_for_forward_config(self):
        for rate in (0, 31.522847522847524, 40, 100, 200):
            for route in audit.bandwidth_routes(rate, self.sets):
                with self.subTest(rate=rate, ports=route['ports']):
                    self.assertAlmostEqual(sum(p['forward_MBps'] for p in route['links']), rate + .01)
                    self.assertAlmostEqual(sum(p['spare_MBps'] for p in route['links']), route['spare_MBps'])
                    self.assertTrue(all(p['spare_MBps'] >= 0 for p in route['links']))
                    self.assertEqual(route['command_return']['spare_percent'], 90)
                    self.assertFalse(route['formally_assigned'])
                    for alt in route['command_alternatives']:
                        self.assertGreaterEqual(alt['forward_spare_MBps'], 0)
                        if 'forward_assignment' in alt:
                            self.assertAlmostEqual(sum(p['MBps'] for p in alt['forward_assignment']), rate + .01)
                            self.assertAlmostEqual(alt['forward_spare_MBps'], route['spare_MBps'] - .01)

    def test_no_unknown_resource_or_WCET_can_become_adopted(self):
        for r in self.rows:
            self.assertIsNone(r['whole_resources'])
            self.assertIsNone(r['CPU_WCET'])
            self.assertIsNone(r['whole_performance_pass'])
            self.assertFalse(r['adopted'])
            self.assertEqual(r['formal_routes'], [])

    def test_n16_storage_failure_is_not_applied_to_N8R8(self):
        self.assertIn('N16_NO_PSRAM_CANNOT_HOLD_5690880_BYTE_TIME_DEINTERLEAVER', self.by_id['S3-T-01f']['reasons'])
        # Reason is specifically N16, not a universal failure of both module choices.
        self.assertEqual(self.by_id['S3-T-000']['reasons'], [])

    def test_recorded_budget_additions_and_deadlines(self):
        r = audit.technical_rechecks()
        self.assertTrue(all(x['arithmetic_equal'] for x in r['archived_20k_allocations']))
        self.assertGreater(r['S_compact_RS_required_MHz'], r['S_best_partial_recorded_MHz'])
        self.assertAlmostEqual(r['K7_shared_T_plus_QPSK_required_MHz'], 151.43424242424243)
        self.assertEqual(r['fft'][-1]['resident_delay_bytes'], 32764)
        self.assertEqual(r['fft'][-1]['hybrid_internal_delay_bytes'], 16380)

    def test_GPIO_framing_memory_and_busy_polling_are_charged(self):
        rows = audit.dedicated_gpio()
        for r in rows:
            self.assertLess(r['framed_budget_capacity_MBps'], r['loop_capacity_MBps'])
            self.assertEqual(r['busy_polling_core_percent'], 100)
            self.assertTrue(r['all_budgets_unmeasured_on_Tang'])
            self.assertFalse(r['assigned'])
        s = next(r for r in rows if r['rate_Msamples_s'] == 40 and r['lanes'] == 2)
        self.assertEqual(s['reorder_full_spill_memory_MBps'], 200)
        self.assertEqual(math.ceil(s['max_ahead_unit_packed_bytes'] / 2048), 20)


if __name__ == '__main__':
    unittest.main()

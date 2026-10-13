"""Check independent arrival/duplex arithmetic and the audit's evidence scope."""
import gzip
import itertools
import json
from fractions import Fraction
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/s3-partition-audit'


class PartitionAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(gzip.decompress((REPORT / 'estimate.json.gz').read_bytes()))
        cls.exact = json.loads((REPORT / 'exact-rs.json').read_text())

    def test_every_whole_stage_ownership_is_present_once(self):
        for standard, count in [('T', 256), ('S', 64)]:
            rows = [r for r in self.data['assignments'] if r['standard'] == standard]
            keys = [tuple(sorted(r['owners'].items())) for r in rows]
            self.assertEqual(len(rows), count)
            self.assertEqual(len(set(keys)), count)
            self.assertTrue(all(r['owners']['RF'] == 'SoC' for r in rows))

    def test_continuous_arrival_and_RF_deduction(self):
        rate = Fraction(28860000 * 2, 203 * 8)
        values = self.data['rates']
        self.assertAlmostEqual(values['RS_codewords_s'], float(rate))
        self.assertAlmostEqual(values['RS_deadline_us'], float(1000000 / rate))
        for cost, cycles in zip(values['S_RF_CPU_model_low_high_Mcycles'],
                                values['S_remaining_aggregate_cycles_per_CW']):
            self.assertAlmostEqual(cycles, (480e6 - cost * 1e6) / float(rate))
            self.assertLess(cycles, 240e6 / float(rate))

    def test_message_overhead_matches_independent_OQ_arithmetic(self):
        octal = 3 * 4096 / (3 * (4096 / 80 + 80 / 640 + .25) + 20)
        quad = 4096 / (4096 / 40 + 80 / 320 + 20)
        period = float(204 * 1000000 / Fraction(28860000 * 2, 203 * 8))
        names = {'SPI2_Octal80', 'SPI3_Quad80'}
        for name, profile in self.exact['profiles'].items():
            sub = self.data['RS_subpartitions'][name]
            rows = [r for r in sub['communication_only_gap0'] if set(r['ports']) == names]
            if name == 'CPU_all_RS':
                self.assertEqual(rows, [])
                continue
            self.assertEqual(len(rows), 1)
            row = rows[0]
            for choice in itertools.product(sorted(names), repeat=len(profile['records'])):
                used = dict.fromkeys(names, 0.)
                for record, port in zip(profile['records'], choice):
                    n = record['pages']
                    used[port] += (n * (4096 / 80 + 80 / 640 + .25) + 20
                                   if 'Octal' in port else n * (4096 / 40 + 80 / 320 + 20)) / period
                margin = octal * (1 - used['SPI2_Octal80']) + quad * (1 - used['SPI3_Quad80']) - 100
                matches = [a for a in row['assignments'] if a['message_ports'] == list(choice)]
                self.assertEqual(len(matches), 1)
                self.assertAlmostEqual(matches[0]['RF_margin_MBps'], margin)

    def test_directions_and_RF_share_actual_port_time(self):
        profiles = {p['name']: p for p in self.data['profiles']}
        for sub in self.data['RS_subpartitions'].values():
            for gap in (0, 8):
                for row in sub[f'communication_only_gap{gap}']:
                    for allocation in row['assignments']:
                        self.assertAlmostEqual(sum(allocation['RF_allocation_MBps']), 100)
                        self.assertGreaterEqual(min(allocation['port_spare_MBps']), -1e-8)
                        for record, port in zip(sub['records'], allocation['message_ports']):
                            expected = 'down' if record['direction'] == 'S3_to_FPGA' else 'up'
                            self.assertIn(profiles[port]['kind'], ('half', expected))
                        for port, rf in zip(row['ports'], allocation['RF_allocation_MBps']):
                            if profiles[port]['kind'] == 'up':
                                self.assertEqual(rf, 0)

    def test_longer_parallel_gap_never_creates_an_assignment(self):
        for sub in self.data['RS_subpartitions'].values():
            def keys(gap):
                return {(tuple(r['ports']), tuple(a['message_ports']))
                        for r in sub[f'communication_only_gap{gap}'] for a in r['assignments']}
            self.assertLessEqual(keys(8), keys(0))

    def test_average_screen_does_not_promote_unknown_performance(self):
        self.assertFalse(self.data['complete_estimate'])
        self.assertFalse(self.data['performance_stage_completed'])
        for row in self.data['assignments']:
            self.assertIsNone(row['performance_pass'])
            self.assertIsNone(row['whole_FPGA_resources'])
            self.assertIsNone(row['CPU_WCET_cycles'])
            self.assertFalse(row['adopted'])
        self.assertEqual(sum(r['CPU_average_model_screen_pass'] for r in self.data['assignments']), 24)


if __name__ == '__main__':
    unittest.main()

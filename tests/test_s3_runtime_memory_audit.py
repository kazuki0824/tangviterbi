import gzip
import importlib.util
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ci'))
from s3_runtime_memory_audit import audit

class RuntimeMemoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not importlib.util.find_spec('elftools'):
            raise unittest.SkipTest('target DWARF audit requires pyelftools')
        cls.profile = ROOT / 'reports/s3-startup-order/sdk/n16r8-late-stacks-heap-flash'
        cls.result = audit(cls.profile)

    def test_target_ABI_accounts_for_previously_omitted_driver_objects(self):
        r = self.result
        self.assertTrue(r['all_scoped_checks_pass'])
        self.assertEqual(r['descriptor_count_per_direction'], 9)
        spi = r['phases']['fresh_vectors']['SPI_live']
        # Independent manual subtotal: old 1696 + GDMA408 + locks320 + IRQ40.
        self.assertEqual(spi['requested_bytes'], 1696 + 408 + 320 + 40)

    def test_calibration_and_timer_lifetimes_are_not_double_counted(self):
        phases = self.result['phases']['fresh_vectors']
        self.assertEqual(phases['PHY_calibration']['requested_bytes'], 2464 + 84 + 1904)
        self.assertEqual(phases['steady']['requested_bytes'], 2464 + 84 + 32)
        self.assertEqual(phases['PHY_calibration']['live_blocks'], 35)

    def test_DMA_pool_payload_is_not_charged_twice(self):
        r = self.result
        self.assertEqual(r['DMA_pool_metadata_single_chunk_lower_bound'], 400)
        link = json.loads((self.profile / 'result.json').read_text())
        pre = link['startup']['allocator_final']['free_before_DMA_pool_upper_bound_bytes']
        steady = r['phases']['fresh_vectors']['steady']
        self.assertEqual(steady['remaining_internal_upper_bound'], pre - 2580 - 140 - 400)

    def test_two_incompatible_config_changes_are_both_reported(self):
        config = json.loads(gzip.decompress((self.profile / 'sdkconfig.json.gz').read_bytes()))
        config['PM_ENABLE'] = True
        config['ESP_PHY_REDUCE_TX_POWER'] = True
        r = audit(self.profile, config)
        failed = {c['name'] for c in r['checks'] if not c['ok']}
        self.assertIn('no_PM_extra_objects', failed)
        self.assertIn('no_reduce_TX_copy', failed)
        self.assertFalse(r['all_scoped_checks_pass'])

    def test_no_NVS_keeps_PHY_calibration_tracking_and_buffer_sizes(self):
        profile = ROOT / 'reports/s3-runtime-memory/sdk/n16r8-late-stacks-heap-flash-no-phy-nvs'
        result = audit(profile)
        self.assertTrue(result['all_scoped_checks_pass'])
        self.assertTrue(result['no_phy_nvs'])
        self.assertEqual(result['calibration_without_NVS'], 'PHY_RF_CAL_FULL')
        before = json.loads((self.profile / 'result.json').read_text())
        after = json.loads((profile / 'result.json').read_text())
        self.assertEqual(before['sizes'], after['sizes'])
        self.assertEqual(before['startup']['main_stack_bytes'], after['startup']['main_stack_bytes'])
        self.assertEqual(result['phases']['fresh_vectors']['steady']['requested_bytes'], 2580)
        self.assertFalse(result['complete_runtime_heap'])
        from elftools.elf.elffile import ELFFile
        import io
        elf = ELFFile(io.BytesIO(gzip.decompress((profile / 's3_raw_probe.elf.gz').read_bytes())))
        symbols = elf.get_section_by_name('.symtab')
        self.assertIsNone(symbols.get_symbol_by_name('nvs_open'))
        self.assertTrue(symbols.get_symbol_by_name('register_chipv7_phy'))
        self.assertTrue(symbols.get_symbol_by_name('phy_track_pll_init'))

    def test_partial_accounting_never_becomes_boot_or_ISR_closure(self):
        r = self.result
        self.assertFalse(r['complete_runtime_heap'])
        self.assertFalse(r['cache_off_ISR_closure_proven'])
        self.assertFalse(r['hardware_boot_executed'])
        self.assertFalse(r['receiver_adopted'])
        self.assertFalse(r['no_phy_nvs'])
        self.assertTrue(any('NVS' in x for x in r['omitted']))

if __name__ == '__main__':
    unittest.main()

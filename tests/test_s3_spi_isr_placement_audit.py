import sys
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ci'))
from s3_spi_isr_placement_audit import audit, audit_symbols, LOCK, OTHER

class SPIISRPlacementTest(unittest.TestCase):
    def test_saved_real_ELF_exposes_all_six_lock_helpers_in_Flash(self):
        result = audit(ROOT / 'reports/s3-runtime-memory/sdk/n16r8-late-stacks-heap-flash-no-phy-nvs')
        failed = {row['symbol'] for row in result['symbols'] if not row['internal_IRAM']}
        self.assertEqual(failed, set(LOCK))
        self.assertFalse(result['bounded_symbol_placement_pass'])
        self.assertFalse(result['SPI_heap_Kconfig_dependency_satisfied'])
        self.assertFalse(result['cache_off_ISR_closure_proven'])

    def test_heap_IRAM_control_passes_placement_and_dependency_conditions(self):
        result = audit(ROOT / 'reports/s3-startup-order/sdk/n16r8-late-stacks')
        self.assertTrue(result['bounded_symbol_placement_pass'])
        self.assertTrue(result['SPI_heap_Kconfig_dependency_satisfied'])
        self.assertFalse(result['receiver_adopted'])

    def test_explicit_lock_placement_does_not_clear_SDK_dependency_violation(self):
        result = audit(ROOT / 'reports/s3-spi-isr-placement/sdk/n16r8-late-stacks-heap-flash-no-phy-nvs-spi-lock-iram')
        self.assertTrue(result['bounded_symbol_placement_pass'])
        self.assertFalse(result['SPI_heap_Kconfig_dependency_satisfied'])
        self.assertFalse(result['cache_off_ISR_closure_proven'])

    def test_raw_only_real_ELF_has_no_SPI_heap_dependency_violation(self):
        result = audit(ROOT / 'reports/s3-raw-only-spi/sdk/n16r8-late-stacks-no-phy-nvs-raw-only-spi')
        self.assertTrue(result['bounded_symbol_placement_pass'])
        self.assertTrue(result['SPI_heap_Kconfig_dependency_satisfied'])
        self.assertFalse(result['receiver_adopted'])

    def test_missing_and_cross_boundary_symbols_are_reported_together(self):
        symbols = {name: (0x40380000, 32, 1) for name in LOCK + OTHER}
        del symbols['spi_intr']
        symbols['gdma_start'] = (0x4039fff0, 32, 1)
        result = audit_symbols(symbols, {'SPI_MASTER_ISR_IN_IRAM': True})
        failed = {c['name'] for c in result['checks'] if not c['ok']}
        self.assertEqual(failed, {'IRAM_spi_intr', 'IRAM_gdma_start', 'SDK_SPI_LOCK_ISR_IRAM'})

    def test_residency_pass_cannot_become_full_closure(self):
        symbols = {name: (0x40380000, 32, 1) for name in LOCK + OTHER}
        result = audit_symbols(symbols, {'SPI_MASTER_ISR_IN_IRAM': True,
                                      'ESP_SPI_BUS_LOCK_ISR_FUNCS_IN_IRAM': True})
        self.assertTrue(result['bounded_symbol_placement_pass'])
        for name in ('cache_off_ISR_closure_proven', 'hardware_boot_executed', 'receiver_adopted'):
            self.assertFalse(result[name])

if __name__ == '__main__':
    unittest.main()

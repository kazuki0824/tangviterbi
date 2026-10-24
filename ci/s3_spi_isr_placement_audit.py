"""Check a bounded SPI ISR symbol set in the target ELF, not a call-graph proof."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
from s3_rom_layout_audit import ELF32

# Read from spi_intr / spi_new_trans / spi_bus_lock in pinned IDF 5.5.1.
# Inlined helpers, indirect calls, literals, assertion paths and ROM are not
# covered by symbol residency. Never promote this list to complete closure.
LOCK = ('spi_bus_lock_bg_entry', 'spi_bus_lock_bg_exit',
        'spi_bus_lock_get_acquiring_dev', 'spi_bus_lock_bg_clear_req',
        'spi_bus_lock_bg_check_dev_acq', 'spi_bus_lock_bg_check_dev_req')
OTHER = ('spi_intr', 'spi_new_trans', 'spi_bus_intr_enable', 'spi_bus_intr_disable',
         'spi_bus_lock_touch', 'spi_bus_lock_get_dev_id',
         'spicommon_dma_desc_setup_link', 'gdma_reset', 'gdma_start',
         'spi_hal_setup_device', 'spi_hal_setup_trans', 'spi_hal_hw_prepare_tx',
         'spi_hal_enable_data_line', 'spi_hal_user_start',
         'esp_intr_enable', 'esp_intr_disable',
         'xQueueGenericSendFromISR', 'xQueueReceiveFromISR')

def audit_symbols(symbols, config):
    checks = []
    def check(name, ok, detail):
        checks.append(dict(name=name, ok=bool(ok), detail=detail))
    check('SDK_SPI_ISR_IRAM', config.get('SPI_MASTER_ISR_IN_IRAM'),
          config.get('SPI_MASTER_ISR_IN_IRAM', False))
    check('SDK_SPI_LOCK_ISR_IRAM', config.get('ESP_SPI_BUS_LOCK_ISR_FUNCS_IN_IRAM'),
          config.get('ESP_SPI_BUS_LOCK_ISR_FUNCS_IN_IRAM', False))
    rows = []
    for name in LOCK + OTHER:
        address, size, _ = symbols.get(name, (0, 0, 0))
        iram = size > 0 and 0x40374000 <= address and address + size <= 0x403a0000
        rows.append(dict(symbol=name, address=hex(address), bytes=size, internal_IRAM=iram))
        check('IRAM_' + name, iram, hex(address))
    return dict(checks=checks, symbols=rows,
                bounded_symbol_placement_pass=all(c['ok'] for c in checks),
                SPI_heap_Kconfig_dependency_satisfied=not (config.get('HEAP_PLACE_FUNCTION_INTO_FLASH', False) and config.get('SPI_MASTER_ISR_IN_IRAM', False)),
                cache_off_ISR_closure_proven=False, hardware_boot_executed=False,
                receiver_adopted=False,
                scope='24 retained SPI normal-path symbols and two configuration conditions; not disassembly or complete graph',
                excluded=['indirect calls and data/literal residency', 'assertion/error paths',
                          'other interrupts and PHY binary/ROM', 'runtime interrupt flags and affinity',
                          'cache-off duration, RF bank deadlines and measured WCET'])

def audit(profile):
    data = gzip.decompress((profile / 's3_raw_probe.elf.gz').read_bytes())
    config = json.loads(gzip.decompress((profile / 'sdkconfig.json.gz').read_bytes()))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'app.elf'; path.write_bytes(data)
        result = audit_symbols(ELF32(path).symbols, config)
    result['ELF_sha256'] = hashlib.sha256(data).hexdigest()
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = audit(args.profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('bounded_symbol_placement_pass', 'cache_off_ISR_closure_proven')}))

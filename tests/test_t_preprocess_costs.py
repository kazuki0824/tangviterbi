"""Independent-failure regression for the linked fee derivation.

The three binary-backed cases run when TPRE_TOOLCHAIN and TPRE_ROM_ELF are
supplied. They deliberately preserve the actual target ELF and alter just
one prerequisite, so a remaining native/HB/tick result is meaningful.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import t_preprocess_runtime_costs as costs


def rows(result):
    return {row['name']:row for row in result['checks']}


def require_enumeration(test, result):
    checked=rows(result)
    for name in costs.REQUIRED:
        test.assertIn('required fee '+name,checked)
    for name in costs.SOURCE_INPUTS:
        test.assertIn('source dependency '+name,checked)
    test.assertIn('required dynamic copy_words',checked)
    test.assertIn('required dynamic fill_words',checked)
    test.assertIn('priced SPI tick and entry paths contain no PIE instructions',checked)
    test.assertEqual(result['status'],'BLOCKED')


class CostEnumerationTests(unittest.TestCase):
    def test_missing_inputs_enumerates_every_source_and_required_event(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            result=costs.build(folder/'toolchain',folder/'missing.elf',folder/'missing-audit.json',
                               folder/'missing-rom.elf',folder/'missing-provenance.json')
        require_enumeration(self,result)
        self.assertEqual(rows(result)['input ELF']['status'],'FAIL')
        self.assertEqual(rows(result)['input ROM']['status'],'FAIL')
        self.assertEqual(rows(result)['required fee TICK1']['status'],'BLOCKED')

    def test_malformed_provenance_does_not_abort_independent_criteria(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);provenance=folder/'provenance.json';provenance.write_text('[]')
            result=costs.build(folder/'toolchain',folder/'missing.elf',folder/'missing-audit.json',
                               folder/'missing-rom.elf',provenance)
        require_enumeration(self,result)
        checked=rows(result)
        self.assertEqual(checked['input provenance']['status'],'FAIL')
        self.assertEqual(checked['static SDK audit uses exact build source manifest']['status'],'BLOCKED')
        self.assertIn('bind support artifact ci/s3_tick_cost_audit.py',checked)


@unittest.skipUnless(os.environ.get('TPRE_TOOLCHAIN') and os.environ.get('TPRE_ROM_ELF'),
                     'actual pinned Xtensa toolchain and ROM supplied by SDK CI')
class LinkedCostEnumerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.toolchain=Path(os.environ['TPRE_TOOLCHAIN'])
        cls.rom=Path(os.environ['TPRE_ROM_ELF'])
        cls.elf=Path(os.environ.get('TPRE_SDK_ELF',costs.OUT/'t_preprocess_integration_probe.elf.gz'))
        cls.audit=Path(os.environ.get('TPRE_SDK_AUDIT',costs.OUT/'audit.json'))
        cls.provenance=Path(os.environ.get('TPRE_SDK_PROVENANCE',costs.OUT/'provenance.json'))

    def run_costs(self,**overrides):
        arguments=dict(tc=self.toolchain,elf=self.elf,sdk_audit=self.audit,rom=self.rom,provenance=self.provenance)
        arguments.update(overrides)
        return costs.build(**arguments)

    def test_missing_rom_preserves_native_halfband_and_owner_fees(self):
        with tempfile.TemporaryDirectory() as directory:
            result=self.run_costs(rom=Path(directory)/'missing-rom.elf')
        require_enumeration(self,result);checked=rows(result)
        self.assertEqual(checked['input ROM']['status'],'FAIL')
        for name in ('NATIVE_BASE','HB_PRODUCE','HB_WORK','OWNER_PHASE','WORKER','FEED'):
            self.assertEqual(checked['required fee '+name]['status'],'PASS',name)
            self.assertIn(name,result['fees'])
        self.assertEqual(checked['required fee TICK1']['status'],'BLOCKED')

    def test_first_sdk_fee_failure_preserves_later_independent_fees(self):
        actual=costs.relocation_map
        def mismatch(old,new,name):
            if name=='spi_device_queue_trans':raise ValueError('injected first SDK function mismatch')
            return actual(old,new,name)
        with patch.object(costs,'relocation_map',side_effect=mismatch):result=self.run_costs()
        require_enumeration(self,result);checked=rows(result)
        self.assertEqual(checked['SDK call closure sdk_queue']['status'],'FAIL')
        self.assertEqual(checked['required fee SPI_SUBMIT']['status'],'BLOCKED')
        for name in ('HB_WORK','FEED','OWNER_PHASE','TICK1','IRQ_COMPLETE'):
            self.assertEqual(checked['required fee '+name]['status'],'PASS',name)
        self.assertEqual(checked['source dependency '+costs.SOURCE_INPUTS[-1]]['status'],'PASS')

    def test_stale_auditor_hash_cannot_produce_ready_ledger(self):
        saved=json.loads(self.audit.read_text());saved['source_auditor_sha256']='0'*64
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'stale-audit.json';path.write_text(json.dumps(saved))
            result=self.run_costs(sdk_audit=path)
        require_enumeration(self,result);checked=rows(result)
        self.assertEqual(checked['static SDK audit uses current auditor']['status'],'FAIL')
        self.assertEqual(checked['static SDK audit uses exact build source manifest']['status'],'PASS')
        self.assertEqual(checked['required fee TICK1']['status'],'PASS')
        self.assertEqual(set(result['fees']),set(costs.REQUIRED))


if __name__=='__main__':unittest.main()

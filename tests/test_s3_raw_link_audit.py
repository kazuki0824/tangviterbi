"""Real saved SDK ELF audits, including corrupted reservations/configuration."""
import gzip
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ci'))
from s3_raw_link_audit import audit
from s3_rom_layout_audit import ELF32

class RawLinkAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom=Path(os.environ['S3_ROM_ELF'])
        if not cls.rom.is_file():raise RuntimeError('S3_ROM_ELF must name the pinned ESP32-S3 rev0 ROM ELF')

    def unpack(self, profile, directory):
        source=ROOT/'reports/s3-raw-sdk'/profile
        for name in ('s3_raw_probe.elf','s3_raw_probe.map','sdkconfig.json'):
            (directory/name).write_bytes(gzip.decompress((source/(name+'.gz')).read_bytes()))
        return (directory/'s3_raw_probe.elf',directory/'s3_raw_probe.map',directory/'sdkconfig.json',self.rom)

    def test_link_success_does_not_override_early_startup_shortage(self):
        for flash in (8,16):
            with self.subTest(flash=flash),tempfile.TemporaryDirectory() as d:
                result=audit(*self.unpack(f'n{flash}r8',Path(d)))
                self.assertTrue(result['all_static_checks_pass'])
                self.assertLess(result['startup']['early_headroom_upper_bound'],0)
                self.assertFalse(result['memory_necessary_pass'])

    def test_relocation_preserves_payload_stack_sizes_and_only_passes_necessary_bound(self):
        for flash in (8,16):
            with self.subTest(flash=flash),tempfile.TemporaryDirectory() as d:
                result=audit(*self.unpack(f'n{flash}r8-late-stacks',Path(d)))
                self.assertTrue(result['memory_necessary_pass'])
                self.assertEqual(result['sizes']['task_stacks'],8192)
                self.assertEqual(sum(int(b,16)-int(a,16) for a,b in result['payload_regions']),131072)
                self.assertFalse(result['hardware_boot_executed'])
                self.assertFalse(result['receiver_adopted'])
                self.assertGreater(result['startup']['allocator_final']['allocator_overhead_lower_bound_bytes'],
                                   result['startup']['allocator_early']['allocator_overhead_lower_bound_bytes'])

    def test_clocked_probe_target_must_match_an_audited_entry(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d)
            source=ROOT/'reports/s3-common-clock/sdk-before/n16r8-late-stacks-no-phy-nvs-raw-only-spi'
            for name in ('s3_raw_probe.elf','s3_raw_probe.map','sdkconfig.json'):
                (directory/name).write_bytes(gzip.decompress((source/(name+'.gz')).read_bytes()))
            args=(directory/'s3_raw_probe.elf',directory/'s3_raw_probe.map',directory/'sdkconfig.json',self.rom)
            good=audit(*args)
            self.assertTrue(good['all_static_checks_pass'])
            self.assertIn('s3_pp_step_clocked',good['hot_symbols'])
            elf=ELF32(args[0]);address=elf.address('raw_keep_clocked_step')
            section=next(s for s in elf.sections if s[1]!=8 and s[3]<=address< s[3]+s[5])
            data=bytearray(args[0].read_bytes());struct.pack_into('<I',data,section[4]+address-section[3],0);args[0].write_bytes(data)
            bad=audit(*args)
            self.assertFalse(bad['all_static_checks_pass'])
            self.assertIn('clocked_entry_known',{c['name'] for c in bad['checks'] if not c['ok']})

    def test_ROM_collision_and_wrong_config_are_both_reported(self):
        with tempfile.TemporaryDirectory() as d:
            args=self.unpack('n16r8-late-stacks',Path(d));elf=ELF32(args[0])
            start=elf.address('soc_reserved_memory_region_start');end=elf.address('soc_reserved_memory_region_end')
            region=elf.read(start,end-start);at=region.index(struct.pack('<II',0x3fce0000,0x3fce8000))
            data=bytearray(args[0].read_bytes());address=start+at+4
            section=next(s for s in elf.sections if s[1]!=8 and s[3]<=address< s[3]+s[5])
            struct.pack_into('<I',data,section[4]+address-section[3],0x3fcf0000);args[0].write_bytes(data)
            config=json.loads(args[2].read_text());config['SPI_MASTER_IN_IRAM']=False;args[2].write_text(json.dumps(config))
            result=audit(*args)
            failed={x['name'] for x in result['checks'] if not x['ok']}
            self.assertIn('ROM_nonoverlap',failed)
            self.assertIn('config_SPI_MASTER_IN_IRAM',failed)
            self.assertFalse(result['all_static_checks_pass'])
            self.assertFalse(result['memory_necessary_pass'])

if __name__=='__main__':unittest.main()

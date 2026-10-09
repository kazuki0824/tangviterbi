from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'experiments'))
from s3_nor_images import package, verify_readback, inspect_fs, Switch, OFFSETS, NEXT, SLOT

def fixture(jump):
    # Parser-only synthetic rows. NOT a valid CRC-bearing FPGA bitstream.
    rows=[bytes.fromhex('ffffffffffffffff'),bytes.fromhex('ffffffffffffffff'),bytes.fromhex('aabbccdd00000000'),
          bytes.fromhex('060000001100481b'),bytes.fromhex('d2000000')+jump.to_bytes(4,'big'),
          bytes.fromhex('3b00000000000001'),bytes(32),bytes.fromhex('0800000000000000')]
    return '// TEST FIXTURE ONLY\n'+'\n'.join(''.join(f'{x:08b}' for x in r) for r in rows)
class NorTest(unittest.TestCase):
    def test_layout_jump_hash_and_rejection(self):
        files={k:fixture(OFFSETS[NEXT[k]]) for k in OFFSETS}
        image,m=package(files);verify_readback(image,m)
        self.assertEqual(len(image),4194304)
        self.assertEqual([e['offset'] for e in m['images']],[0,524288,1048576])
        with self.assertRaises(ValueError):verify_readback(bytes([image[0]^1])+image[1:],m)
        bad=dict(files);bad['S']=fixture(0)
        with self.assertRaises(ValueError):package(bad)
        with self.assertRaises(ValueError):inspect_fs(fixture(1))
        with self.assertRaises(ValueError):inspect_fs(fixture(1<<24))
        with self.assertRaises(ValueError):inspect_fs(fixture(0)+'\n'+'0'*(SLOT*8))
        with self.assertRaises(ValueError):package({'T':files['T']})
    def test_switch_two_hops_and_fresh_epoch(self):
        s=Switch(current='S');self.assertEqual(s.request('T',0),'stop_RF_mute_TS_drain_DMA')
        self.assertEqual(s.tick(1),'none');self.assertEqual(s.tick(2,quiescent=True),'pulse_RECONFIG_N')
        self.assertEqual(s.tick(300,image='recovery',identity_ok=True),'pulse_RECONFIG_N')
        self.assertEqual(s.tick(600,image='T',identity_ok=True),'reset_streams_set_epoch')
        self.assertEqual(s.epoch,2);self.assertEqual(s.tick(601,locked=True),'none')
        self.assertEqual(s.tick(602,epoch_ack=True),'tune_RF')
        self.assertEqual(s.tick(700,locked=True),'enable_RF_TS')
    def test_failure_never_restarts_RF(self):
        for kind in ('drain','boot_timeout','wrong_image','wrong_identity','epoch','lock','epoch_wrap'):
            with self.subTest(kind=kind):
                s=Switch(epoch=65535 if kind=='epoch_wrap' else 1);s.request('S',0)
                if kind=='drain':s.tick(100000)
                elif kind=='epoch_wrap':pass
                else:
                    s.tick(1,quiescent=True)
                    if kind=='boot_timeout':s.tick(2000001)
                    else:
                        s.tick(10,image='T' if kind=='wrong_image' else 'S',identity_ok=kind!='wrong_identity')
                        if kind=='epoch':s.tick(100010)
                        elif kind=='lock':s.tick(11,epoch_ack=True);s.tick(5000011)
                self.assertEqual(s.state,'fault');self.assertEqual(s.tick(9000000,locked=True),'none')

"""Independent conservation and negative boundary cases for bank/queue model."""
import importlib.util
from pathlib import Path
import unittest
import subprocess
import tempfile

p=Path(__file__).resolve().parents[1]/'experiments/s3_batch_bank_closure.py'
spec=importlib.util.spec_from_file_location('batch_closure',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class BatchBankTests(unittest.TestCase):
    def test_full_stream_conservation_with_nonintegral_batch_tail(self):
        for n in (1,2,17,1024):
            with self.subTest(banks=n):
                r=m.simulate(banks=n)
                self.assertFalse(r['faults'])
                self.assertEqual(r['produced_bytes'],12288*n*20//8)
                self.assertEqual(r['retired_bytes'],r['completed_batches']*32768)
                self.assertEqual(r['tail_bytes'],r['produced_bytes']%32768)
                self.assertEqual(r['retired_bytes']+r['tail_bytes'],r['produced_bytes'])
    def test_ring_reuse_is_by_contiguous_completion_not_dispatch(self):
        r=m.simulate(ring=65536)
        self.assertTrue(any(f['kind']=='ring_capacity' for f in r['faults']))
        good=m.simulate()
        self.assertGreater(good['peak_completed_out_of_order_bytes'],0)
        self.assertGreater(good['peak_ring_bytes'],65536)
    def test_bank_lease_negative_control(self):
        r=m.simulate(extra_delay=200)
        self.assertTrue(any(f['kind']=='bank_lease' for f in r['faults']))
        self.assertGreater(r['packing_latency_us'],r['bank_lease_us'])
    def test_wire_or_queue_pass_does_not_override_cpu_fail(self):
        r=m.simulate(api_us=60)
        self.assertTrue(r['optimistic_trace_pass'])
        self.assertGreater(r['aggregate_CPU_percent'],100)
        self.assertFalse(r['divisible_CPU_necessary_pass'])
        self.assertFalse(r['combined_necessary_pass'])
    def test_existing_wire_encoder_rejects_large_transactions(self):
        root=p.parents[1]
        source='#include "s3_transport.h"\nint main(void) {\n s3_wire_header h;\n if(s3_wire_make(&h,S3_RF,1,0,4096)!=S3_OK) return 1;\n if(s3_wire_make(&h,S3_RF,1,0,16384)!=S3_RANGE) return 2;\n if(s3_wire_make(&h,S3_RF,1,0,32768)!=S3_RANGE) return 3;\n return 0;\n}\n'
        with tempfile.TemporaryDirectory() as temp:
            c=Path(temp)/'wire.c';c.write_text(source)
            exe=Path(temp)/'wire'
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',str(root/'experiments'),str(c),str(root/'experiments/s3_transport.c'),'-o',str(exe)],check=True,capture_output=True,text=True)
            subprocess.run([str(exe)],check=True,capture_output=True,text=True)
    def test_additional_delay_cannot_improve_bank_margin(self):
        a=m.simulate(extra_delay=0);b=m.simulate(extra_delay=100)
        self.assertAlmostEqual(a['lease_margin_us']-b['lease_margin_us'],100)
        self.assertFalse(a['full_receiver_pass'])

if __name__=='__main__':unittest.main()

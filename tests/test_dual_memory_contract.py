"""Independent conservation and concrete counterexamples for memory admission."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from dual_memory_contract import audit, groups, CAPACITY

class MemoryContract(unittest.TestCase):
    def test_complement_and_payload_conservation(self):
        for mode in (1,2,3):
            r=1 << (mode-1); I=16//r
            g=groups(mode,[(13,I)])
            self.assertEqual(sum(g.values()),13*96*r*6)
            # Equal population of all 96 delays, same maximum-depth capacity
            # in every transmission mode: sum(0..95)*I*carriers-per-delay*6.
            self.assertEqual(sum(d*n for d,n in g.items()),5690880)
            for i in range(96*r):
                tx=I*((5*i)%96)
                self.assertIn(95*I-tx,g)

    def test_real_capacity_counterexample(self):
        row=audit(1,[(1,4),(1,8),(11,16)],'aligned_group')
        self.assertEqual(row['T_ring_bytes'],7888896)
        self.assertGreater(row['total_reserved_bytes'],CAPACITY)
        self.assertFalse(row['capacity_pass'])

    def test_unbounded_queue_counterexample(self):
        row=audit(3,[(13,4)],'carrier_padded')
        self.assertGreater(row['total_bus_MBps'],row['optimistic_service_MBps'])
        self.assertGreater(row['overload_growth_min_bytes_per_ms'],0)

    def test_dense_storage_is_not_free_bandwidth(self):
        layers=[(1,4),(1,8),(11,16)]
        dense=audit(1,layers,'compact_group_masked')
        aligned=audit(1,layers,'aligned_group')
        self.assertLess(dense['T_ring_bytes'],aligned['T_ring_bytes'])
        self.assertGreater(dense['T_bus_MBps'],aligned['T_bus_MBps'])
        self.assertFalse(dense['implemented'])

    def test_bypass(self):
        row=audit(3,[(13,0)],'aligned_group')
        self.assertEqual(row['T_ring_bytes'],0)
        self.assertEqual(row['T_bus_MBps'],0)

if __name__=='__main__':unittest.main()

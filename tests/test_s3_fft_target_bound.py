"""Verify the CFG lower bound and its restriction to a specific scalar object."""
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ci'))
from s3_fft_target_bound import parse,minimum_memory_path

class FFTTargetBoundTest(unittest.TestCase):
 def test_minimize_memory_instead_of_shortest_instruction_path(self):
  ops={0:('beqz','a2, 8 <loop+8>'),2:('l32i','a3, a1, 0'),
   4:('j','c <loop+c>'),8:('add','a2, a2, a2'),10:('add','a3, a3, a3'),
   12:('s16i','a3, a4, 0')}
  cost,path=minimum_memory_path(ops,0,12)
  self.assertEqual(cost,1);self.assertEqual(path,[0,8,10,12])
 def test_committed_object_bound_is_recomputed_from_every_branch(self):
  out=ROOT/'reports/s3-fft-target-bound'
  functions=parse((out/'fft-O3.disasm').read_text())
  report=json.loads((out/'results.json').read_text())
  for name,value in report['results'].items():
   cost,path=minimum_memory_path(functions[name],int(value['loop_start_hex'],16),int(value['loop_end_hex'],16))
   self.assertEqual(cost,value['minimum_scalar_memory_instructions_per_butterfly'])
   self.assertEqual([f'{x:x}' for x in path],value['witness_path_hex'])
   self.assertEqual(value['memory_issue_cycles_lower_bound'],cost*13*4096)
   self.assertGreater(value['ideal_two_core_240MHz_us_lower_bound'],1039.5)
  self.assertFalse(report['CPU_WCET_verified']);self.assertFalse(report['receiver_adopted'])
 def test_unknown_control_transfers_do_not_get_zero_cost_paths(self):
  with self.assertRaises(ValueError):minimum_memory_path({0:('call0','4 <callee>'),4:('s16i','a3, a4, 0')},0,4)

if __name__=='__main__':unittest.main()

import unittest
from ci.gowin_control_capacity_audit import signature,audit

def ff(t='DFFRE',ce=2,reset=3,d=4):
 return dict(type=t,connections=dict(CLK=[1],CE=[ce],RESET=[reset],D=[d]))
class ControlAuditTest(unittest.TestCase):
 def test_backend_compatible_set_reset_pair(self):
  a=ff();b=ff('DFFSE');b['connections']['SET']=b['connections'].pop('RESET')
  self.assertEqual(signature(a),signature(b))
  self.assertNotEqual(signature(a),signature(ff(reset=8)))
  self.assertNotEqual(signature(a),signature(ff(ce=8)))
  self.assertNotEqual(signature(a),signature(ff('DFFCE')))
 def test_odd_groups_and_one_driver_one_ff(self):
  c={'a':ff(),'b':ff(),'c':ff(ce=9),'alu':dict(type='ALU',connections={'SUM':[4]}),'ram':dict(type='RAM16SDP4',connections={})}
  r=audit(c)
  self.assertEqual(r['control_groups'],2)
  self.assertEqual(r['control_pair_slot_lower_bound'],4)
  self.assertEqual(r['maximum_ALU_FF_pairings_ignoring_control'],1)
  self.assertEqual(r['six_slice_lower_bound'],9)

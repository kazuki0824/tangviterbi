import unittest
from ci.gowin_materialize_ff_inputs import transform,verify

def cell(t,ports):return dict(type=t,connections=ports)
def graph(cells):return {'modules':{'top':{'attributes':{'top':'1'},'cells':cells,'netnames':{}}}}
class IdentityTest(unittest.TestCase):
 def test_shared_driver_and_ff_chain(self):
  g=graph({'l':cell('LUT2',{'F':[3],'I0':[1],'I1':[2]}),'a':cell('DFF',{'D':[3],'Q':[4]}),'b':cell('DFFE',{'D':[3],'Q':[5],'CE':[6]}),'c':cell('DFF',{'D':[4],'Q':[7]})})
  r,t,x=transform(g);self.assertEqual(len(x),2);verify(g,r,t,x)
 def test_alu_sum_is_retained_but_carry_is_buffered(self):
  g=graph({'alu':cell('ALU',{'SUM':[3],'COUT':[4]}),'a':cell('DFF',{'D':[3],'Q':[5]}),'b':cell('DFF',{'D':[4],'Q':[6]})})
  r,t,x=transform(g);self.assertEqual([i['ff']for i in x],['b'])
 def test_control_change_is_rejected(self):
  g=graph({'a':cell('DFFE',{'D':[1],'Q':[2],'CE':[3]})});r,t,x=transform(g);r['modules']['top']['cells']['a']['connections']['CE']=[4]
  with self.assertRaises(AssertionError):verify(g,r,t,x)

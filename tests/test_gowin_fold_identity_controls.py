import json,shutil,subprocess,tempfile,unittest
from pathlib import Path
from ci.gowin_fold_identity_controls import fold
ROOT=Path(__file__).resolve().parents[1]
class FoldControlsTest(unittest.TestCase):
 def fixture(self,t):
  conn=dict(D=[2],Q=[3],CLK=[4],CE=[5]);dirs={p:'output'if p=='Q'else'input'for p in conn}
  if t=='DFFRE':conn['RESET']=[6];dirs['RESET']='input'
  return {'modules':{'shared_receiver_fft_tile_probe':{'cells':{'ff':dict(type=t,parameters={'INIT':'1'},attributes={},connections=conn,port_directions=dirs),'ff_input_identity_0':dict(type='LUT1',parameters={'INIT':'10'},attributes={},connections={'I0':[1],'F':[2]},port_directions={'I0':'input','F':'output'})}}}}
 def test_no_other_consumers_permitted(self):
  m=self.fixture('DFFE');m['modules']['shared_receiver_fft_tile_probe']['cells']['extra']=dict(type='LUT1',connections={'I0':[2],'F':[7]},port_directions={'I0':'input','F':'output'})
  with self.assertRaises(AssertionError):fold(m)
 @unittest.skipUnless(shutil.which('iverilog'),'Icarus required')
 def test_against_pinned_yosys_primitive_models(self):
  models=ROOT.parent/'toolchain/oss-cad-suite/share/yosys/gowin/cells_sim.v'
  for t in ['DFFE','DFFRE']:
   out,records=fold(self.fixture(t));cells=out['modules']['shared_receiver_fft_tile_probe']['cells'];lut=cells['ff_input_identity_0'];self.assertEqual(cells['ff']['parameters']['INIT'],'1')
   width=4 if t=='DFFRE'else 3;reset=',.RESET(r)'if width==4 else'';i3=',.I3(r)'if width==4 else''
   tb=f'''module tb;
reg clk=0,d=0,ce=0,r=0;wire oldq,newq,nd;integer q,v;
{t} #(.INIT(1'b1)) old(.Q(oldq),.D(d),.CLK(clk),.CE(ce){reset});
LUT{width} #(.INIT({1<<width}'b{lut['parameters']['INIT']})) lut(.F(nd),.I0(d),.I1(newq),.I2(ce){i3});
DFF #(.INIT(1'b1)) replacement(.Q(newq),.D(nd),.CLK(clk));
initial begin
#1;if(oldq!==newq)$fatal(1,"init");
for(q=0;q<2;q=q+1)for(v=0;v<8;v=v+1)begin
clk=0;d=q;ce=1;r=0;#1;clk=1;#1;clk=0;
d=v&1;ce=(v>>1)&1;r=(v>>2)&1;#1;
if(oldq!==newq)$fatal(1,"between edges");
clk=1;#1;if(oldq!==newq)$fatal(1,"transition q=%0d v=%0d",q,v);
end
$display("PASS {t} all states/inputs and INIT");$finish;end endmodule'''
   with tempfile.TemporaryDirectory()as x:
    p=Path(x);(p/'tb.v').write_text(tb)
    r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(models),str(p/'tb.v')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
    r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(r.stdout)

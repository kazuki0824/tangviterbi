"""Compositional proof: unchanged arbiter, one-hot selection, arbitrary-row lookup identity."""
import hashlib,json,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(shutil.which('yosys'),'Yosys required')
class LookaheadTest(unittest.TestCase):
 def run_yosys(self,script):
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp)/'check.ys';p.write_text(script)
   r=subprocess.run(['yosys','-Q','-s',str(p)],cwd=ROOT,capture_output=True,text=True,timeout=120)
   print(r.stdout,flush=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_arbiter_body_unchanged_and_onehot(self):
  for suffix in ['', '_metadata']:
   name=f'experiments/sdram_client_arbiter_lookahead{suffix}.sv';s=(ROOT/name).read_text()
   restored=s.replace(' input wire [255:0] rsp_data,output wire [5:0] request_selected\n',' input wire [255:0] rsp_data\n').replace(' assign request_selected=selected;\n','')
   restored=re.sub(r'`ifdef FORMAL.*?`endif\n','',restored,flags=re.S)
   self.assertEqual(restored,(ROOT/f'experiments/sdram_client_arbiter_tile_grace{suffix}.sv').read_text())
   module='sdram_client_arbiter'+suffix
   self.run_yosys(f'read_verilog -formal -sv {name}\nprep -top {module} -flatten\nchformal -lower\nsat -seq 4 -set-init-zero -tempinduct -prove-asserts -verify\n')
 def test_lookup_and_unchanged_controller_state_machine(self):
  p=ROOT/'experiments/dual_sdram_client_lookahead.sv';s=p.read_text()
  a=s.index(' // Evaluate each source before arbitration.');b=s.index(' // Accept the next descriptor',a);lookup=s[a:b]
  old='''     if(open[req_address[9:8]])begin
      if(row[req_address[9:8]]==req_address[20:10])state<=req_write?WCMD:RCMD;
      else state<=PRE;
     end else state<=ACT;'''
  new='''     if(selected_hit)state<=req_write?WCMD:RCMD;
     else if(selected_open)state<=PRE;
     else state<=ACT;'''
  restored=(s[:a]+s[b:]).replace(new,old).replace('output reg[31:0] dq_out,input wire[31:0] dq_in,\n input wire[125:0] client_lookup_address,input wire[5:0] request_selected);','output reg[31:0] dq_out,input wire[31:0] dq_in);')
  self.assertEqual(restored,(ROOT/'experiments/dual_sdram_refresh_predecode.sv').read_text())
  formal='''module lookup_proof(input wire[125:0] client_lookup_address,input wire[5:0] request_selected,input wire[43:0] rows,input wire[3:0] open);
 wire[10:0] row[0:3];
 genvar b;generate for(b=0;b<4;b=b+1)begin: rowsplit
  assign row[b]=rows[b*11+:11];
 end endgenerate
 reg[20:0]req_address;integer i;
 always @* begin
  req_address=0;
  for(i=0;i<6;i=i+1)req_address=req_address|({21{request_selected[i]}}&client_lookup_address[i*21+:21]);
 end
'''+lookup+'''
 always @* begin
  assume((request_selected & (request_selected-6'd1))==0);
  if(request_selected!=0)begin
   assert(selected_open==open[req_address[9:8]]);
   assert(selected_hit==(open[req_address[9:8]]&&(row[req_address[9:8]]==req_address[20:10])));
  end
 end
endmodule
'''
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp)/'lookup.sv';p.write_text(formal)
   self.run_yosys(f'read_verilog -formal -sv {p}\nprep -top lookup_proof -flatten\nchformal -lower\nsat -set-assumes -prove-asserts -verify\n')

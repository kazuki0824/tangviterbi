"""Cycle miter under held-request contract; invalid metadata is don't-care."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class MetadataArbiterTest(unittest.TestCase):
 def test_same_handshakes_and_accepted_requests(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp);(d/'tb.sv').write_text(TB)
   p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(d/'sim'),str(ROOT/'rtl/sdram_client_arbiter.sv'),str(ROOT/'experiments/sdram_client_arbiter_metadata.sv'),str(d/'tb.sv')],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stderr)
   p=subprocess.run(['vvp',str(d/'sim')],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stdout+p.stderr);print(p.stdout)
TB=r'''module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0;reg[5:0]cv=0,cw=0,csr=0;reg[125:0]ca=0;reg[1535:0]cd=0;reg[191:0]cm=0;
reg ready=0,sv=0;reg[255:0]sd=0;
wire[5:0]cr[0:1],csv[0:1];wire[255:0]csd[0:1],data[0:1];wire valid[0:1],wr[0:1],sr[0:1];wire[20:0]addr[0:1];wire[31:0]mask[0:1];
sdram_client_arbiter a(clk,rst,cv,cr[0],cw,ca,cd,cm,csv[0],csr,csd[0],valid[0],ready,wr[0],addr[0],data[0],mask[0],sv,sr[0],sd);
sdram_client_arbiter_metadata b(clk,rst,cv,cr[1],cw,ca,cd,cm,csv[1],csr,csd[1],valid[1],ready,wr[1],addr[1],data[1],mask[1],sv,sr[1],sd);
reg[31:0]rng=32'h1029513;reg[5:0]accepted=0;integer cycle=0,requests=0,responses=0,i,j;reg outstanding=0;
function[31:0]next(input[31:0]x);begin next=(x<<1)^((x[31])?32'h04c11db7:0);end endfunction
always @(posedge clk)if(rst)begin
 if({cr[0],csv[0],valid[0],sr[0],csd[0]}!=={cr[1],csv[1],valid[1],sr[1],csd[1]})$fatal(1,"handshake cycle %d",cycle);
 if(valid[0] && {wr[0],addr[0],data[0],mask[0]}!=={wr[1],addr[1],data[1],mask[1]})$fatal(1,"metadata cycle %d",cycle);
 accepted<=cr[0]&cv;
 if(valid[0]&&ready)begin outstanding<=1;requests=requests+1;end
 if(sv&&sr[0])begin outstanding<=0;responses=responses+1;end
end
always @(negedge clk)begin
 cycle=cycle+1;rng=next(rng);
 rst=cycle>=4 && !(cycle>=10000 && cycle<10004);
 if(!rst)begin cv=0;sv=0;outstanding=0;accepted=0;end
 else begin
  for(i=0;i<6;i=i+1)begin
   if(accepted[i])cv[i]=0;
   rng=next(rng);
   if(!cv[i]&&rng[0])begin
    cv[i]=1;cw[i]=rng[1];ca[i*21+:21]=rng[22:2];
    for(j=0;j<8;j=j+1)begin rng=next(rng);cd[i*256+j*32+:32]=rng;end
    rng=next(rng);cm[i*32+:32]=rng;
   end
  end
  ready=rng[2];csr=rng[8:3];
  if(!outstanding)sv=0;else if(rng[9])sv=1;
 end
 if(cycle==20000)begin
  if(requests<500||responses<500)$fatal(1,"insufficient traffic");
  $display("PASS cycles=%0d requests=%0d responses=%0d",cycle,requests,responses);$finish;
 end
end
endmodule'''

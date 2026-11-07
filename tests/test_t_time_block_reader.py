import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TB=r'''
module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0,sv=0,qr=0,rv=0,oready=0;wire sr,qv,rr,ov,done;wire[20:0]qa;wire[7:0]od;
reg[22:0]base=1024,start=0;reg[23:0]ending=1312;reg[255:0]data;
t_time_block_reader dut(clk,rst,sv,sr,base,ending,start,qv,qr,qa,rv,rr,data,ov,oready,od,done);
integer cycle=0,pending=-1,held=0,j,count=0,offset=0,trial,requests=0,checks=0;
reg active=0;reg[7:0]expected;
always @(negedge clk)begin
 qr=pending<0 && cycle%7!=0;oready=cycle%11<7;
 rv=pending>=0 && cycle>=pending;
 if(rv)for(j=0;j<32;j=j+1)data[j*8+:8]=(held+j)%251;
end
always @(posedge clk)begin
 cycle=cycle+1;
 if(rst)begin
  if(qv&&qr)begin
   if(qa[2:0]!=0 || qa*4<base || qa*4>=ending)$fatal(1,"address");
   held=qa*4;pending=cycle+3+(cycle%5);requests=requests+1;
  end
  if(rv&&rr)pending=-1;
  if(ov&&oready)begin
   expected=(base+(offset+count)%(ending-base))%251;
   if(od!==expected)$fatal(1,"data trial=%0d count=%0d",trial,count);
   count=count+1;checks=checks+1;
  end
 end
end
initial begin
 repeat(3)@(negedge clk);rst=1;
 for(trial=0;trial<576;trial=trial+1)begin
  if(trial==288)begin base=8388320;ending=8388608;end
  offset=trial%288;start=base+offset;count=0;requests=0;
  @(negedge clk);sv=1;@(negedge clk);sv=0;
  while(!done)@(negedge clk);
  if(count!=96 || requests<3 || requests>4)$fatal(1,"counts");
 end
 $display("CHECKED_BYTES %0d",checks);$finish;
end
initial begin #3000000;$fatal(1,"timeout");end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class ReaderTest(unittest.TestCase):
 def test_offsets_wrap_and_stalls(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(TB)
   r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(ROOT/'experiments/t_time_block_reader.sv'),str(p/'tb.sv')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=60)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('CHECKED_BYTES 55296',r.stdout)
   print(r.stdout)
if __name__=='__main__':unittest.main()

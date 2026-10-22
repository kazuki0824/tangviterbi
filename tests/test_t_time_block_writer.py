import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TB=r'''
module tb;
reg clk=0;always #5 clk=~clk;
reg rst=0,sv=0,iv=0,qr=0,rv=0;wire sr,ir,qv,rr,done;wire[20:0]qa;wire[255:0]qd;
reg[22:0]base=1024,start=0;reg[23:0]ending=1312;reg[7:0]id;
t_time_block_writer dut(clk,rst,sv,sr,base,ending,start,iv,ir,id,qv,qr,qa,qd,rv,rr,done);
integer cycle=0,pending=-1,sent=0,bursts=0,trial,j,checks=0,expected_address;
always @(negedge clk)begin
 qr=pending<0&&cycle%7!=0;rv=pending>=0&&cycle>=pending;
 iv=sent<96&&cycle%5!=0;id=(trial*17+sent)%251;
end
always @(posedge clk)begin
 cycle=cycle+1;
 if(rst)begin
  if(iv&&ir)sent=sent+1;
  if(qv&&qr)begin
   expected_address=base+(start-base+bursts*32)%(ending-base);
   if(qa*4!=expected_address)$fatal(1,"address");
   for(j=0;j<32;j=j+1)begin
    if(qd[j*8+:8]!==8'((trial*17+bursts*32+j)%251))$fatal(1,"byte order");
    checks=checks+1;
   end
   bursts=bursts+1;pending=cycle+2+cycle%9;
  end
  if(rv&&rr)pending=-1;
 end
end
initial begin
 repeat(3)@(negedge clk);rst=1;
 for(trial=0;trial<72;trial=trial+1)begin
  if(trial==36)begin base=8388320;ending=8388608;end
  start=base+(trial%9)*32;sent=0;bursts=0;
  @(negedge clk);sv=1;@(negedge clk);sv=0;
  while(!done)@(negedge clk);
  if(sent!=96||bursts!=3)$fatal(1,"count");
 end
 $display("CHECKED_BYTES %0d",checks);$finish;
end
initial begin #1000000;$fatal(1,"timeout");end
endmodule
'''
@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class WriterTest(unittest.TestCase):
 def test_wrap_stalls_and_packing(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'tb.sv').write_text(TB)
   r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(p/'sim'),str(ROOT/'experiments/t_time_block_writer.sv'),str(p/'tb.sv')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run(['vvp',str(p/'sim')],capture_output=True,text=True,timeout=60)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('CHECKED_BYTES 6912',r.stdout);print(r.stdout)
if __name__=='__main__':unittest.main()

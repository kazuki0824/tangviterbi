"""Native payload bytes, I80 framing, CDC/backpressure and epoch faults."""
from pathlib import Path
import random
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]

class LCD16RxTest(unittest.TestCase):
 def simulate(self,out,tb):
  (out/'tb.sv').write_text(tb)
  p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(ROOT/'rtl/s3_async_fifo.sv'),str(ROOT/'rtl/s3_lcd16_rx.sv'),str(out/'tb.sv')],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
  p=subprocess.run(['vvp','sim'],cwd=out,capture_output=True,text=True,timeout=30)
  (out/'simulation.log').write_text(p.stdout+p.stderr)
  self.assertEqual(p.returncode,0,p.stdout+p.stderr)
  self.assertIn('PASS',p.stdout)

 def test_native_bytes_under_core_stalls(self):
  out=ROOT/'build/s3-lcd16-rx';out.mkdir(parents=True,exist_ok=True)
  rng=random.Random(16040);beats=[];expected=[]
  for page in range(6):
   cmd=0xd711 if page%2==0 else 0xd712;offset=page*4096
   beats.extend([cmd,17,offset>>16,offset&65535,4096,0,0,0])
   payload=rng.randbytes(4096)
   beats.extend(int.from_bytes(payload[i:i+2],'little') for i in range(0,4096,2))
   expected.extend([(1<<32)|(cmd<<16)|17,(2<<32)|offset,(3<<32)|4096])
   expected.extend(((8<<32) if i==4092 else 0)|int.from_bytes(payload[i:i+4],'little') for i in range(0,4096,4))
  (out/'beats.hex').write_text(''.join(f'{v:04x}\n' for v in beats))
  (out/'tokens.hex').write_text(''.join(f'{v:09x}\n' for v in expected))
  self.simulate(out,'''`timescale 1ns/1ps
module tb;
reg clk=0;always #5.050505 clk=~clk;
reg wr=0,cs=0,dc=0,rst=1,ready=1;reg[15:0]dq=0;
wire valid,fault;wire[35:0]token;
s3_lcd16_rx #(.FIFO_AW(5)) dut(wr,cs,dc,clk,rst,dq,valid,ready,token,fault);
reg[15:0]beats[0:12335];reg[35:0]want[0:6161];
reg[31:0]rng=32'had817246;reg stalled=0;reg[35:0]hold;
integer p,i,got=0;
always @(negedge clk)begin rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);ready=rng[2:0]!=0;end
always @(posedge clk)if(rst)begin
 if(fault)$fatal(1,"unexpected fault");
 if(stalled&&(!valid||token!==hold))$fatal(1,"stall instability");
 stalled=valid&&!ready;hold=token;
 if(valid&&ready)begin
  if(got>=6162||token!==want[got])$fatal(1,"token %0d got=%h expected=%h",got,token,want[got]);
  got=got+1;
 end
end
initial begin
 $readmemh("beats.hex",beats);$readmemh("tokens.hex",want);
 #1;rst=0;#1;cs=1;#38;rst=1;#100;
 for(p=0;p<6;p=p+1)begin
  cs=0;
  for(i=0;i<2056;i=i+1)begin
   dc=i>=8;dq=beats[p*2056+i];#12.5;wr=1;#12.5;wr=0;
  end
  cs=1;#8000;
 end
 #1000;if(got!=6162)$fatal(1,"missing tokens=%0d",got);
 $display("PASS 40MHz LCD16 / 99MHz core / 24576 unchanged payload bytes / tokens=%0d",got);$finish;
end
endmodule''')

 def test_faults_survive_cs_and_clear_only_at_epoch_reset(self):
  out=ROOT/'build/s3-lcd16-faults';out.mkdir(parents=True,exist_ok=True)
  self.simulate(out,'''`timescale 1ns/1ps
module tb;
reg clk=0;always #5.050505 clk=~clk;
reg wr=0,cs=0,dc=0,rst=1,ready=1;reg[15:0]dq=0;
wire valid,fault;wire[35:0]token;
s3_lcd16_rx #(.FIFO_AW(2)) dut(wr,cs,dc,clk,rst,dq,valid,ready,token,fault);
integer mode,i;
task beat(input[15:0]w,input bit data_phase);begin dq=w;dc=data_phase;#12.5;wr=1;#12.5;wr=0;end endtask
task reset_epoch;begin cs=1;rst=0;#100;rst=1;#100;if(fault)$fatal(1,"reset fault");end endtask
initial begin
 #1;rst=0;#1;cs=1;#38;rst=1;
 for(mode=0;mode<4;mode=mode+1)begin
  reset_epoch;ready=mode!=3;cs=0;
  beat(16'hd711,0);beat(17,0);beat(0,0);beat(0,0);beat(4096,0);
  beat(mode==0?1:0,0);beat(0,0);beat(0,0);
  for(i=0;i<(mode==2?2049:64);i=i+1)beat(i,mode!=1);
  cs=1;#100;if(!fault)$fatal(1,"missing fault mode=%0d",mode);
  cs=0;#100;cs=1;#100;if(!fault)$fatal(1,"CS cleared fault");
 end
 ready=1;reset_epoch;
 $display("PASS reserved header / DC mismatch / frame overrun / FIFO overflow / epoch reset");$finish;
end
endmodule''')

if __name__=='__main__':unittest.main()

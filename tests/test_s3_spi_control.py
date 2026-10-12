"""Mode-0 status snapshots and stopped epoch rules; actual RTL wires."""
from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class ControlTest(unittest.TestCase):
 def test_status_and_epoch(self):
  out=ROOT/'build/s3-spi-control';out.mkdir(parents=True,exist_ok=True)
  tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0,clock_run=1;always #5.555 if(clock_run)clk=~clk;
reg rst=1,idle=1,locked=0,fault=0,iq=0;reg[31:0]offset=0;
wire[15:0]ep;wire er,en,cf;reg sck=0,cs=0;reg[3:0]di=0;wire[3:0]dout;wire oe;
s3_spi_control #(.IMAGE_ID(1),.BUILD_TAG(32'h1234abcd)) dut(clk,rst,idle,locked,fault,iq,offset,ep,er,en,cf,sck,cs,di,dout,oe);
wire rv,rf;wire[35:0]tok;
s3_spi_rx #(.LANES(4),.IGNORE_IQ_READ(1),.IGNORE_CONTROL(1)) rx(sck,cs,clk,rst,oe?dout:di,rv,1'b1,tok,rf);
integer resets=0;reg[31:0]w[0:7];reg[7:0]b;
always @(posedge clk)begin if(er)resets=resets+1;if(rst&&(rv||rf))$fatal(1,"control leaked to write FIFO");end
 task send(input[7:0]x);begin
 di=x>>4;#6.25;sck=1;if(oe)$fatal(1,"driving header");#6.25;sck=0;
 di=x;#6.25;sck=1;if(oe)$fatal(1,"driving header");#6.25;sck=0;
 end endtask
 task header(input[15:0]cmd,input[15:0]e,input[31:0]arg,input[15:0]length);begin
 cs=0;send(cmd>>8);send(cmd);send(e>>8);send(e);send(arg>>24);send(arg>>16);send(arg>>8);send(arg);send(length>>8);send(length);di=0;
 end endtask
 task command(input[15:0]cmd,input[15:0]e,input[31:0]arg);begin header(cmd,e,arg,0);cs=1;repeat(12)@(negedge clk);end endtask
 task reset;begin rst=0;cs=0;sck=0;resets=0;repeat(5)@(negedge clk);cs=1;rst=1;repeat(5)@(negedge clk);end endtask
 task unacknowledged_query(input[31:0]nonce);integer i;begin
 header('hd71c,0,nonce,32);
 for(i=0;i<64;i=i+1)begin #6.25;sck=1;if(oe)$fatal(1,"old snapshot accepted without fresh core ACK");#6.25;sck=0;end
 cs=1;#100;
 end endtask
 task query(input[31:0]nonce);integer i;begin
 header('hd71c,0,nonce,32);
 for(i=0;i<32;i=i+1)begin
 #6.25;sck=1;if(!oe)$fatal(1,"missing reply");b=dout<<4;#6.25;sck=0;
 #6.25;sck=1;if(!oe)$fatal(1,"missing body");b=b|dout;#6.25;sck=0;
 w[i/4]=(w[i/4]>>8)|({24'd0,b}<<24);offset=offset+4096;iq=!iq;
 end
 cs=1;repeat(6)@(negedge clk);
 if(w[0]!=32'h31534353||w[4]!=nonce||w[5]!=32'h1234abcd||w[7]||w[6]!=(w[0]^w[1]^w[2]^w[3]^w[4]^w[5]^32'h96c39a5f))$fatal(1,"snapshot checksum/nonce");
 end endtask
 initial begin
 reset();query(32'h12345678);if(w[1]!=32'h01010000||en||cf)$fatal(1,"cold identity");
 @(negedge clk);clock_run=0;
 unacknowledged_query(9);unacknowledged_query(10);
 clock_run=1;repeat(10)@(negedge clk);query(11);
 command('hd71d,17,32'h45504f43);if(ep!=17||resets!=1||en||cf)$fatal(1,"epoch reset");
 command('hd71d,17,32'h45504f43);if(resets!=1)$fatal(1,"duplicate reset erased owner");
 offset=4096;iq=1;query(2);if(w[1]!=32'h01010011||w[2]!=4096||w[3]!=5)$fatal(1,"coherent ready snapshot");
 locked=1;command('hd71e,17,1);if(!en||cf)$fatal(1,"locked enable");fault=1;repeat(4)@(negedge clk);if(en)$fatal(1,"fault not muted");
 reset();fault=0;locked=0;command('hd71d,17,32'h45504f43);command('hd71e,17,1);if(!cf||en)$fatal(1,"unlocked enable accepted");
 reset();idle=0;command('hd71d,18,32'h45504f43);if(ep||!cf||resets)$fatal(1,"live owners clobbered");
 reset();idle=1;command('hd71d,18,32'h45504f43);command('hd71d,17,32'h45504f43);if(ep!=18||!cf||resets!=1)$fatal(1,"stale epoch");
 $display("PASS actual control wires, coherent snapshots, nonce, epoch ACK, lock, mute, invalid reset");$finish;
 end
 initial begin #1000000;$fatal(1,"deadlock");end
endmodule'''
  (out/'tb.sv').write_text(tb)
  subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),*[str(ROOT/'rtl'/(s+'.sv')) for s in ('s3_async_fifo','s3_spi_rx','s3_spi_control')],str(out/'tb.sv')],check=True)
  r=subprocess.run(['vvp',str(out/'sim')],capture_output=True,text=True,timeout=30)
  (out/'simulation.log').write_text(r.stdout+r.stderr);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()

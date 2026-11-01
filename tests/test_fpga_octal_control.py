"""Exercise unchanged Quad control and a real Octal in-band command/status wire."""
import subprocess, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class OctalControl(unittest.TestCase):
    def test_old_quad(self):
        subprocess.run(["python3","-m","unittest","tests.test_s3_spi_control","-v"],cwd=ROOT,check=True)
    def test_octal(self):
        out=ROOT/"build/fpga-octal-control";out.mkdir(parents=True,exist_ok=True)
        tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,cs=1,sck=0,idle=1,locked=1,fault=0;
reg[7:0] di=0;wire[7:0] dout;wire oe;
wire[15:0]epoch;wire er,en,cf;
s3_spi_control #(.IMAGE_ID(0),.BUILD_TAG(32'h1234abcd),.LANES(8)) dut(
.clk(clk),.resetn(rst),.streams_idle(idle),.locked(locked),
.receiver_fault(fault),.iq_ready(1'b0),.iq_offset(32'd0),
.epoch(epoch),.epoch_reset(er),.stream_enable(en),.control_fault(cf),
.spi_clk(sck),.cs_n(cs),.dq_in(di),.dq_out(dout),.dq_oe(oe));
always #5 clk=~clk;
task send(input [7:0] b);begin
 di=b;#8;sck=1;#8;sck=0;
end endtask
task header(input[15:0]cmd,input[15:0]ep,input[31:0]arg,input[15:0]length);begin
 cs=0;send(cmd>>8);send(cmd);send(ep>>8);send(ep);
 send(arg>>24);send(arg>>16);send(arg>>8);send(arg);
 send(length>>8);send(length);
end endtask
task command(input[15:0]cmd,input[15:0]ep,input[31:0]arg);begin
 header(cmd,ep,arg,0);cs=1;repeat(12)@(negedge clk);
end endtask
reg[7:0] bytes[0:31];reg[31:0]w[0:7];integer i;
task query(input[31:0]nonce);begin
 header(16'hd71c,0,nonce,32);
 for(i=0;i<32;i=i+1)begin
 #8;sck=1;
 if(!oe)$fatal(1,"octal reply not enabled");
 bytes[i]=dout;
 #8;sck=0;
 end
 cs=1;repeat(12)@(negedge clk);
 for(i=0;i<8;i=i+1)w[i]={bytes[i*4+3],bytes[i*4+2],bytes[i*4+1],bytes[i*4]};
 if(w[0]!=32'h31534353||w[4]!=nonce||w[5]!=32'h1234abcd||w[7]||w[6]!=(w[0]^w[1]^w[2]^w[3]^w[4]^w[5]^32'h96c39a5f))
 $fatal(1,"octal status mismatch magic=%h nonce=%h expected=%h",w[0],w[4],nonce);
end endtask
always @(posedge sck) if(!cs && dut.beat==9) $display("OCTAL HEADER cmd=%h epoch=%h arg=%h len=%h beat=%d",dut.next_header[79:64],dut.next_header[63:48],dut.next_header[47:16],dut.next_header[15:0],dut.beat);
initial begin
 repeat(5)@(negedge clk);rst=1;repeat(5)@(negedge clk);
 query(32'h12345678);if(epoch||en||cf)$fatal(1,"bad cold state");
 command(16'hd71d,17,32'h45504f43);
 if(epoch!=17||cf)$fatal(1,"epoch command failed ep=%d cf=%b en=%b",epoch,cf,en);
 query(32'h11223344);if(w[1]!=32'h01000011)$fatal(1,"wrong epoch");
 command(16'hd71e,17,1);
 if(!en||cf)$fatal(1,"enable command failed");
 query(32'h11223345);if(!(w[3]&16))$fatal(1,"enable not in status");
 command(16'hd71e,17,0);
 if(en||cf)$fatal(1,"stop failed");
 $display("PASS octal in-band control query/nonce/epoch/enable/stop");
 $finish;
end
initial begin #2000000;$fatal(1,"timeout");end
endmodule
'''
        (out/"tb.sv").write_text(tb)
        cp=subprocess.run(["iverilog","-g2012","-s","tb","-o",str(out/"sim"),str(ROOT/"rtl/s3_spi_control.sv"),str(out/"tb.sv")],capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr)
        p=subprocess.run(["vvp",str(out/"sim")],capture_output=True,text=True,timeout=30)
        (out/"run.log").write_text(p.stdout+p.stderr)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
if __name__=="__main__":unittest.main()

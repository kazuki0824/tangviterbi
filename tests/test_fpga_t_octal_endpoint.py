"""Bit-exact SPI2 Octal RF and in-band CSR/credit shared physical pins."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class TOctalEndpoint(unittest.TestCase):
    def test_shared_octal_rf_control_credit(self):
        out=ROOT/"build/fpga-t-octal-endpoint";out.mkdir(parents=True,exist_ok=True)
        tb=r'''\`timescale 1ns/1ps
module tb;
reg clk=0,rst=1,sck=0,cs=1,frontend_idle=1,locked=1;
always #5 clk=~clk;
tri[7:0]bus;
reg drive=1;reg[7:0]host_data=0;
assign bus=drive?host_data:8'hzz;
wire rv,rl,en,fault;wire[31:0] rd,offset;
wire[15:0]ep;reg rr=1;
s3_spi_t_octal_control_endpoint dut(
 .clk(clk),.resetn(rst),.frontend_idle(frontend_idle),
 .frontend_locked(locked),.frontend_fault(1'b0),
 .spi2_clk(sck),.spi2_cs_n(cs),.spi2_d(bus),
 .RF_valid(rv),.RF_ready(rr),.RF_data(rd),
 .RF_offset(offset),.RF_last(rl),
 .stream_enable(en),.fault(fault),.epoch(ep));
function automatic[31:0] sample(input integer index);
 sample=(index*32'h01010203)^32'ha5ac9f13;
endfunction
reg accepting=0;
integer received=0;
always @(posedge clk)if(accepting)begin
 if(fault)$fatal(1,"endpoint fault");
 if(rv&&rr)begin
  if(received>=1024 || rd!==sample(received) || offset!==0 ||
      rl!==(received==1023))
   $fatal(1,"RF word mismatch n=%0d data=%h expected=%h",received,rd,sample(received));
  received=received+1;
 end
end
task send(input[7:0]data);begin
 drive=1;host_data=data;#8;sck=1;#8;sck=0;
end endtask
task header(input[15:0]cmd,input[15:0]epoch,input[31:0]argument,input[15:0]length);begin
 drive=1;cs=0;
 send(cmd>>8);send(cmd);send(epoch>>8);send(epoch);
 send(argument>>24);send(argument>>16);send(argument>>8);send(argument);
 send(length>>8);send(length);
end endtask
task command(input[15:0]cmd,input[15:0]epoch,input[31:0]argument);begin
 header(cmd,epoch,argument,0);
 cs=1;repeat(12)@(negedge clk);
end endtask
reg[7:0]reply[0:31];reg[31:0]w[0:7];
integer i;
task query(input[31:0]nonce);begin
 header(16'hd71c,0,nonce,32);drive=0;
 for(i=0;i<32;i=i+1)begin
  #8;sck=1;
  if(bus===8'hzz)$fatal(1,"missing FPGA octal reply");
  reply[i]=bus;
  #8;sck=0;
 end
 cs=1;drive=1;repeat(12)@(negedge clk);
 for(i=0;i<8;i=i+1)w[i]={reply[i*4+3],reply[i*4+2],reply[i*4+1],reply[i*4]};
 if(w[0]!=32'h31534353 || w[4]!=nonce ||
    w[6]!=(w[0]^w[1]^w[2]^w[3]^w[4]^w[5]^32'h96c39a5f))
  $fatal(1,"invalid status snapshot");
end endtask
task writepage;integer n;reg[31:0]word;begin
 header(16'hd711,17,0,4096);
 for(n=0;n<1024;n=n+1)begin
   word=sample(n);
   send(word);send(word>>8);send(word>>16);send(word>>24);
 end
 cs=1;repeat(12)@(negedge clk);
end endtask
initial begin
 rst=0;repeat(6)@(negedge clk);rst=1;repeat(8)@(negedge clk);
 query(32'hc0ffee11);
 if(ep!=0||en||fault)$fatal(1,"initial state");
 command(16'hd71d,17,32'h45504f43);
 if(ep!=17||fault)$fatal(1,"epoch command failed");
 command(16'hd71e,17,1);
 if(!en||fault)$fatal(1,"enable command failed");
 accepting=1;
 writepage();
 wait(received==1024);
 repeat(20)@(negedge clk);
 query(32'hc0ffee12);
 if((w[3]>>5&7)!=1)$fatal(1,"credit not published in status %h",w[3]);
 if(ep!=17||!en||fault)$fatal(1,"state after transfer");
 command(16'hd71e,17,0);
 if(en||fault)$fatal(1,"stop failed");
 command(16'hd71d,18,32'h45504f43);
 query(32'hc0ffee13);
 if(ep!=18||(w[3]>>5&7)!=0||fault)$fatal(1,"epoch did not reset Gray credit");
 $display("PASS T SPI2 Octal one physical bus: command, RF 4096 bytes, status Gray credit, drain and epoch");
 $finish;
end
initial begin #1500000;$fatal(1,"timeout/deadlock");end
endmodule
'''
        (out/"tb.sv").write_text(tb)
        sources=("s3_async_fifo","s3_spi_rx","s3_page_guard","s3_pooled_page_store",
                 "s3_rf_credit","s3_spi_control","s3_spi_t_octal_control_endpoint")
        cmd=["iverilog","-g2012","-s","tb","-o",str(out/"sim"),
             *[str(ROOT/"rtl"/(name+".sv")) for name in sources],str(out/"tb.sv")]
        cp=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(cp.returncode,0,cp.stderr)
        result=subprocess.run(["vvp",str(out/"sim")],capture_output=True,text=True,timeout=40)
        (out/"run.log").write_text(result.stdout+result.stderr)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn("PASS T SPI2 Octal one physical bus",result.stdout)

if __name__=="__main__":unittest.main()

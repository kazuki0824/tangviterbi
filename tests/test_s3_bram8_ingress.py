"""Native 100 MB/s ingress with consumption credits on both RF ports.

Synthetic ingress-only workload; not a complete FIR/FEC receiver. One batch
of capture lookahead is assumed. API delays follow the old rate contract.
"""
import subprocess
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class IngressTest(unittest.TestCase):
    def test_native_stream_and_credit_publication(self):
        out=ROOT/'build/s3-bram8-ingress';out.mkdir(parents=True,exist_ok=True)
        tb=r'''`timescale 1ns/1ps
module BUFG(input wire I,output wire O);assign O=I;endmodule
module tb;
reg clk=0;always #5.555555 clk=~clk;
reg rst=1,sck=0,cs=0,wr=0,lcs=0,dc=0;
reg[7:0] din=0;reg[15:0] ld=0;
wire valid,last,fault;wire[31:0] data,offset;wire[19:0] frontier;wire global_sck;
wire[7:0] sd;wire soe,sfault;
s3_bram2_memory_bridge #(.PIPE_WINDOW(1),.SLOT_BITS(3),.FIXED_ARBITER(1)) bridge(
 clk,rst,16'd7,sck,cs,din,wr,lcs,dc,ld,valid,1'b1,data,last,offset,fault,frontier,global_sck);
s3_spi_page_status #(.WINDOW(8)) status(
 clk,rst,16'd7,frontier,fault,global_sck,cs,din,sd,soe,sfault);
integer got=0,known=0,next_seq=0,max_used=0,queries=0;
reg[31:0] expected;
always @(posedge clk)if(rst)begin
 if(fault||sfault)$fatal(1,"receiver fault at word %d",got);
 if(valid)begin
  expected=32'h40000000|((got/1024)<<12)|(got%1024);
  if(data!==expected||offset!==((got/1024)*4096)||last!==(got%1024==1023))
   $fatal(1,"word %d data=%h want=%h offset=%h last=%b",got,data,expected,offset,last);
  got=got+1;
 end
end
task reserve(input integer seq,input integer pages);integer used;begin
 if(seq!=next_seq)$fatal(1,"global seq mismatch");
 used=next_seq-known+pages;
 if(used>8)$fatal(1,"credit exhaustion: used=%d",used);
 if(used>max_used)max_used=used;
 next_seq=next_seq+pages;
end endtask
task spi_beat(input[7:0] b);begin din=b;#6.25;sck=1;#6.25;sck=0;end endtask
task header(input[15:0] cmd,input integer offset_bytes,input integer length);begin
 spi_beat(cmd[15:8]);spi_beat(cmd[7:0]);spi_beat(0);spi_beat(7);
 spi_beat((offset_bytes>>24)&255);spi_beat((offset_bytes>>16)&255);
 spi_beat((offset_bytes>>8)&255);spi_beat(offset_bytes&255);
 spi_beat((length>>8)&255);spi_beat(length&255);
end endtask
task spi_page(input integer seq);integer i;reg[31:0] v;begin
 cs=0;header(16'hd711,seq*4096,4096);
 for(i=0;i<1024;i=i+1)begin
  v=32'h40000000|(seq<<12)|i;
  spi_beat(v[7:0]);spi_beat(v[15:8]);spi_beat(v[23:16]);spi_beat(v[31:24]);
 end
 cs=1;#250;
end endtask
task query;integer i,f;reg[127:0] reply;reg[63:0] value;begin
 cs=0;header(16'hd71c,0,16);repeat(16)spi_beat(0);reply=0;
 for(i=0;i<16;i=i+1)begin
  #6.25;sck=1;
  if(!soe)$fatal(1,"status not driven");reply={reply[119:0],sd};
  #6.25;sck=0;
 end
 cs=1;#250;value=reply[127:64];
 if(reply[63:0]!==~value||value[63:48]!=16'hc7a1||value[47:32]!=7||
    value[11:8]!=8||value[7:0]!=0)$fatal(1,"status invalid %h",reply);
 f=value[31:12];
 if(f<known||f>next_seq)$fatal(1,"stale or forged frontier %d",f);
 known=f;queries=queries+1;
end endtask
task lcd_beat(input[15:0] b,input bit d);begin
 ld=b;dc=d;#12.5;wr=1;#12.5;wr=0;
end endtask
task lcd_page(input integer seq);integer i;reg[31:0] v;begin
 lcs=0;lcd_beat(16'hd711,0);lcd_beat(7,0);
 lcd_beat((seq*4096)>>16,0);lcd_beat((seq*4096)&65535,0);
 lcd_beat(4096,0);repeat(3)lcd_beat(0,0);
 for(i=0;i<1024;i=i+1)begin
  v=32'h40000000|(seq<<12)|i;lcd_beat(v[15:0],1);lcd_beat(v[31:16],1);
 end
 lcs=1;
end endtask
integer ob,lb;realtime start,base;
initial begin
 #1;rst=0;#1;cs=1;lcs=1;#49;rst=1;#100;
 // Startup query precedes all RF reservations. Eight iterations, 32 pages.
 query;start=$realtime+100;
 fork
  begin
   for(ob=0;ob<8;ob=ob+1)begin
    base=start+ob*163840;#(base-$realtime+1);
    reserve(ob*4+1,2);#19999;
    spi_page(ob*4+1);spi_page(ob*4+2);
    #20000;query;
   end
  end
  begin
   for(lb=0;lb<8;lb=lb+1)begin
    #(start+lb*163840-$realtime);
    reserve(lb*4,1);#8000;lcd_page(lb*4);
    reserve(lb*4+3,1);#8000;lcd_page(lb*4+3);
   end
  end
 join
 #100000;query;
 if(got!=32*1024||known!=32||max_used>8||queries!=10)
  $fatal(1,"unfinished: words=%d frontier=%d max=%d queries=%d",got,known,max_used,queries);
 $display("PASS native 100 MB/s, 32 pages, actual frontier status, max credit=%0d",max_used);
 $finish;
end
endmodule
'''
        (out/'tb.sv').write_text(tb)
        sources=['s3_async_fifo','s3_spi_rx','s3_lcd16_rx','s3_page_guard',
                 's3_page_reorder','s3_rx_page_store','s3_bram2_memory_bridge','s3_spi_page_status']
        p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim')]+[
            str(ROOT/'rtl'/f'{s}.sv') for s in sources]+[str(out/'tb.sv')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        p=subprocess.run(['vvp','sim'],cwd=out,capture_output=True,text=True,timeout=60)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertIn('PASS native 100 MB/s',p.stdout)

if __name__=='__main__': unittest.main()

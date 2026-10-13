"""Continuous ISDB-T IQ cadence with concurrent producer/SPI bank ownership."""
import hashlib
import json
from pathlib import Path
import random
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]

class PingPongTest(unittest.TestCase):
    def test_other_bank_ack_does_not_cancel_truncated_bank_timeout(self):
        out=ROOT/'build/s3-iq-pingpong/timeout';out.mkdir(parents=True,exist_ok=True)
        tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;reg rst=1,bv=0,wv=0;wire br,wr,sent,fault;wire[1:0] pr;
reg[31:0] off=0;reg sck=0,cs=0;reg[3:0] qi=0;wire[3:0] qo;wire oe;
s3_spi_iq_pingpong dut(clk,rst,bv,br,16'd17,off,wv,wr,32'habcd1234,pr,sent,fault,1'b0,sck,cs,qi,qo,oe);
integer p,i,n=0;always @(posedge clk)if(sent)n=n+1;
task send_byte(input[7:0] x);begin
 qi=x>>4;#6.25;sck=1;#6.25;sck=0;qi=x;#6.25;sck=1;#6.25;sck=0;
end endtask
task header(input[31:0] a);begin
 cs=0;send_byte('hd7);send_byte('h1b);send_byte(0);send_byte(17);
 send_byte(a>>24);send_byte(a>>16);send_byte(a>>8);send_byte(a);send_byte('h10);send_byte(0);
end endtask
initial begin
 #1;rst=0;#1;cs=1;repeat(4)@(negedge clk);rst=1;
 for(p=0;p<2;p=p+1)begin
  @(negedge clk);if(!br)$fatal(1,"bank not free");off=p*4096;bv=1;
  @(negedge clk);bv=0;wv=1;repeat(1024)@(negedge clk);wv=0;
 end
 repeat(4)@(negedge clk);if(pr!=3||br)$fatal(1,"both banks not held");
 header(0);repeat(17)send_byte(0);cs=1;#250;
 header(4096);repeat(4096)send_byte(0);cs=1;
 repeat(10)@(negedge clk);
 if(fault||n!=1||pr!=1||br)$fatal(1,"wrong bank ack ownership");
 repeat(33000)@(negedge clk);
 if(!fault||br||wr||pr||oe||n!=1)$fatal(1,"bank 1 ack hid bank 0 timeout");
 $display("PASS independent bank timeout and retained ownership");$finish;
end
endmodule'''
        (out/'tb.sv').write_text(tb)
        c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(ROOT/'rtl/s3_spi_iq_pingpong.sv'),str(out/'tb.sv')],text=True,capture_output=True)
        self.assertEqual(c.returncode,0,c.stderr)
        r=subprocess.run(['vvp','sim'],cwd=out,text=True,capture_output=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        (out/'simulation.log').write_text(r.stdout)

    def test_symbol_cadence_with_guard_interval(self):
        out=ROOT/'build/s3-iq-pingpong';out.mkdir(parents=True,exist_ok=True)
        raw=random.Random(91482).randbytes(16*4096)
        (out/'input.hex').write_text(''.join(f'{int.from_bytes(raw[i:i+4],"little"):08x}\n' for i in range(0,len(raw),4)))
        tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0;always #5.050505 clk=~clk;
reg rst=1,bv=0,wv=0,abort=0;wire br,wr,sent,fault;wire[1:0] pr;
reg[31:0] off=0,wd=0;reg sck=0,cs=0;reg[3:0] qi=0;wire[3:0] qo;wire oe;
s3_spi_iq_pingpong dut(clk,rst,bv,br,16'd17,off,wv,wr,wd,pr,sent,fault,abort,sck,cs,qi,qo,oe);
reg[31:0] data[0:16383];integer p,w,q,i,k,f,phase=0,sent_count=0,overlap=0;reg[7:0] b;
realtime first_start,deadline;
always @(posedge clk)if(rst)begin
 if(sent)sent_count=sent_count+1;
 if(fault)$fatal(1,"unexpected IQ fault p=%d q=%d",p,q);
 if(wv&&oe)overlap=overlap+1;
end
task send_byte(input[7:0] x);begin
 qi=x>>4;#6.25;sck=1;#6.25;sck=0;
 qi=x;#6.25;sck=1;#6.25;sck=0;
end endtask
task header(input[31:0] a);begin
 cs=0;send_byte('hd7);send_byte('h1b);send_byte(0);send_byte(17);
 send_byte(a>>24);send_byte(a>>16);send_byte(a>>8);send_byte(a);send_byte('h10);send_byte(0);qi=0;
end endtask
task read_byte(output[7:0] x);begin
 #6.25;sck=1;if(!oe)$fatal(1,"missing high nibble");x={qo,4'b0};#6.25;sck=0;
 #6.25;sck=1;if(!oe)$fatal(1,"missing low nibble");x[3:0]=qo;#6.25;sck=0;
end endtask
initial begin
 $readmemh("input.hex",data);f=$fopen("output.hex","w");
 #1;rst=0;#1;cs=1;repeat(4)@(negedge clk);rst=1;
 fork
  begin
   for(p=0;p<16;p=p+1)begin
    @(negedge clk);while(!br)@(negedge clk);off=p*4096;bv=1;
    @(negedge clk);bv=0;
    for(w=0;w<1024;w=w+1)begin
     while(phase<6237)begin @(negedge clk);phase=phase+512;end
     phase=phase-6237;
     if(!wr)$fatal(1,"producer bank lost");
     wd=data[p*1024+w];wv=1;
     @(negedge clk);wv=0;phase=phase+512;
    end
    if(p==7)#31500; // 256 GI samples at 512/63 MHz, one symbol per 8 pages
   end
  end
  begin
   wait(pr[0]);#20000;first_start=$realtime;
   for(q=0;q<16;q=q+1)begin
    deadline=first_start+q*129937.5;
    if($realtime>deadline+0.001)$fatal(1,"SPI missed slot");
    #(deadline-$realtime);
    if(!pr[q%2])$fatal(1,"IQ page unavailable at fixed deadline page=%d",q);
    header(q*4096);
    for(i=0;i<4096;i=i+1)begin read_byte(b);$fdisplay(f,"%02x",b);end
    cs=1;
   end
  end
 join
 repeat(10)@(negedge clk);$fclose(f);
 if(sent_count!=16||overlap<1000||pr!=0||!br)$fatal(1,"ownership/overlap");
 $display("PASS bytes=65536 sent=%0d concurrent_fill_beats=%0d page_period_ns=129937.5",sent_count,overlap);$finish;
end
initial begin #3000000;$fatal(1,"deadline/deadlock");end
endmodule'''
        (out/'tb.sv').write_text(tb)
        c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(ROOT/'rtl/s3_spi_iq_pingpong.sv'),str(out/'tb.sv')],text=True,capture_output=True)
        self.assertEqual(c.returncode,0,c.stderr)
        r=subprocess.run(['vvp','sim'],cwd=out,text=True,capture_output=True,timeout=45)
        (out/'simulation.log').write_text(r.stdout+r.stderr)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        got=bytes(int(x,16) for x in (out/'output.hex').read_text().split())
        self.assertEqual(hashlib.sha256(got).hexdigest(),hashlib.sha256(raw).hexdigest())
        (out/'result.json').write_text(json.dumps(dict(pages=16,bytes=len(raw),output=r.stdout.strip(),
            producer_active_sample_rate_Msps=512/63,GI_samples_after_8_pages=256,
            page_period_us=129.9375,payload_MBps=4096/129.9375,
            scope='two page banks and an ideal preformed GI-removed IQ producer; no real filter/FFT/S3 scheduler',
            receiver_adopted=False),indent=2)+'\n')

if __name__=='__main__':unittest.main()

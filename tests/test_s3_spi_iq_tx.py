"""Full pages through mode-0 wires, plus no-SCK completion and abort ownership."""
from pathlib import Path
import json
import random
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

class IQTxTest(unittest.TestCase):
    def test_page_data_and_fault_lifetimes(self):
        cases = []
        for lanes in (4, 8):
            out = ROOT / f'build/s3-spi-iq-tx/{lanes}'
            out.mkdir(parents=True, exist_ok=True)
            rng = random.Random(0x1b00+lanes)
            raw = rng.randbytes(8*4096)
            words = [int.from_bytes(raw[i:i+4], 'little') for i in range(0,len(raw),4)]
            (out/'input.hex').write_text(''.join(f'{w:08x}\n' for w in words))
            tb = r'''`timescale 1ns/1ps
module tb;
reg clk=0;always #5.050505 clk=~clk;
reg rst=1,bv=0,wv=0,abort=0;wire br,wr,pr,sent,fault;
reg[15:0] ep=17;reg[31:0] off=0,wd=0;
reg sck=0,cs=0;reg[LANES-1:0] qi=0;wire[LANES-1:0] qo;wire oe;
s3_spi_iq_tx #(.LANES(LANES)) dut(clk,rst,bv,br,ep,off,wv,wr,wd,pr,sent,fault,abort,sck,cs,qi,qo,oe);
wire rx_valid,rx_fault;wire[35:0]rx_token;
s3_spi_rx #(.LANES(LANES),.IGNORE_IQ_READ(1)) rx(sck,cs,clk,rst,oe?qo:qi,rx_valid,1'b1,rx_token,rx_fault);
reg[31:0] data[0:8191];integer p,i,f,sent_count=0;
reg[7:0] b;
always @(posedge clk) if(sent)sent_count=sent_count+1;
always @(posedge clk) if(rst&&(rx_valid||rx_fault))$fatal(1,"IQ read leaked into write endpoint");
task reset;begin
 #1;rst=0;#1;cs=1;bv=0;wv=0;abort=0;sck=0;repeat(4)@(negedge clk);rst=1;repeat(4)@(negedge clk);sent_count=0;
end endtask
task load(input integer page);integer k;begin
 @(negedge clk);if(!br)$fatal(1,"producer blocked after completion");
 ep=17;off=4096*page;bv=1;
 @(negedge clk);bv=0;
 for(k=0;k<1024;k=k+1)begin
  if(k%17==0)begin wv=0;@(negedge clk);end
  if(!wr)$fatal(1,"fill permission missing");wd=data[page*1024+k];wv=1;@(negedge clk);
 end
 wv=0;repeat(4)@(negedge clk);
 if(!pr||br||wr||fault)$fatal(1,"page not immutable/published");
end endtask
task send_byte(input[7:0] x);integer k;begin
 for(k=8-LANES;k>=0;k=k-LANES)begin
  qi=x>>k;#6.25;sck=1;
  if(oe)$fatal(1,"driving during master header");
  #6.25;sck=0;
 end
end endtask
task header(input[15:0] e,input[31:0] a);begin
 cs=0;send_byte('hd7);send_byte('h1b);send_byte(e>>8);send_byte(e);
 send_byte(a>>24);send_byte(a>>16);send_byte(a>>8);send_byte(a);
 send_byte('h10);send_byte(0);qi=0;
end endtask
task read_byte(output[7:0] x);integer k;begin
 x=0;
 for(k=0;k<8/LANES;k=k+1)begin
  #6.25;sck=1;
  if(!oe)$fatal(1,"missing IQ lane/dummy clock needed");
  if(br||wr)$fatal(1,"RAM became writable while SPI owned it");
  x=(x<<LANES)|qo;#6.25;sck=0;
 end
end endtask
initial begin
 $readmemh("input.hex",data);f=$fopen("output.hex","w");reset();
 for(p=0;p<8;p=p+1)begin
  load(p);header(17,4096*p);
  for(i=0;i<4096;i=i+1)begin read_byte(b);$fdisplay(f,"%02x",b);end
  cs=1;repeat(10)@(negedge clk); // completion MUST cross with SCK stopped
  if(fault||!br||pr||sent_count!=p+1||oe)$fatal(1,"last edge completion");
 end
 $fclose(f);
 reset();load(0);header(16,0);cs=1;repeat(10)@(negedge clk);
 if(!fault||br||oe)$fatal(1,"stale epoch not poisoned");
 reset();load(0);header(17,4096);cs=1;repeat(10)@(negedge clk);
 if(!fault||br||oe)$fatal(1,"wrong offset not poisoned");
 reset();load(0);header(17,0);for(i=0;i<17;i=i+1)read_byte(b);cs=1;
 repeat(33000)@(negedge clk);
 if(!fault||br||sent_count||oe)$fatal(1,"truncated page released/timeout missing");
 reset();header(17,0);cs=1;repeat(10)@(negedge clk);
 if(!fault||oe)$fatal(1,"unpublished page read");
 reset();load(0);abort=1;repeat(4)@(negedge clk);
 if(!fault||br||pr)$fatal(1,"abort did not retain page");
 reset();load(0);header(17,0);for(i=0;i<4096;i=i+1)read_byte(b);
 send_byte(0);cs=1;repeat(10)@(negedge clk);
 if(!fault||oe)$fatal(1,"extra payload clocks not poisoned");
 $display("PASS 8 pages, no-SCK completion, six fault cases, lanes=LANES");$finish;
end
initial begin #10000000;$fatal(1,"test deadlock");end
endmodule'''.replace('LANES',str(lanes)).replace('.'+str(lanes)+'(','.LANES(')
            (out/'tb.sv').write_text(tb)
            c = subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),
                str(ROOT/'rtl/s3_async_fifo.sv'),str(ROOT/'rtl/s3_spi_rx.sv'),
                str(ROOT/'rtl/s3_spi_iq_tx.sv'),str(out/'tb.sv')],text=True,capture_output=True)
            self.assertEqual(c.returncode,0,c.stderr)
            r = subprocess.run(['vvp','sim'],cwd=out,text=True,capture_output=True,timeout=45)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            received=bytes(int(x,16) for x in (out/'output.hex').read_text().split())
            self.assertEqual(received,raw)
            cases.append(dict(lanes=lanes,pages=8,checked_payload_bytes=len(raw),SPI_MHz=80,
                core_MHz=99,output=r.stdout.strip()))
        (ROOT/'build/s3-spi-iq-tx/result.json').write_text(json.dumps(dict(cases=cases,
            scope='page RAM and SPI wires; status transport, S3 firmware and IO STA not included',
            receiver_adopted=False),indent=2)+'\n')

if __name__=='__main__':
    unittest.main()

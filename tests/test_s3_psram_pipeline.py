"""Actual Octal/Quad wires through DDR pin models to ordered native words."""
import hashlib
import json
from pathlib import Path
import random
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class PsramPipelineTest(unittest.TestCase):
    def test_two_spi_ports_through_physical_memory_protocol(self):
        out=ROOT/'build/s3-psram-pipeline';out.mkdir(parents=True,exist_ok=True)
        rng=random.Random(724016)
        wire=[bytearray(),bytearray()];raw=bytearray()
        pages=96
        for p in range(pages):
            data=rng.randbytes(4096);raw.extend(data)
            port=int(p%3==2)
            wire[port].extend(bytes.fromhex('d7110011')+(p*4096).to_bytes(4,'big')+b'\x10\x00'+data)
        for p in range(2):
            (out/f'wire{p}.hex').write_text(''.join(f'{x:02x}\n' for x in wire[p]))
        (out/'expected.hex').write_text(''.join(f'{int.from_bytes(raw[i:i+4],"little"):08x}\n' for i in range(0,len(raw),4)))
        tb=r'''`timescale 1ns/1ps
module BUFG(input I,output O);assign O=I;endmodule
module tb;
reg clk=0,clk_ck=0;always #5.050505 clk=~clk;
initial begin #2.5252525;forever #5.050505 clk_ck=~clk_ck;end
reg rst=1,s0=0,s1=0,c0=0,c1=0;reg[7:0] d0=0;reg[3:0] d1=0;
wire valid,last,init,fault;reg ready=0;wire[31:0] data,offset;
wire[1:0] ck,ckn,cs,rreset;wire[15:0] dq;wire[1:0] rwds;
s3_spi_memory_bridge dut(clk,clk_ck,rst,16'd17,s0,c0,d0,s1,c1,d1,
 valid,ready,data,last,offset,init,fault,ck,ckn,cs,rreset,dq,rwds);
w955_ddr_model #(.OUTPUT_DELAY(1.0),.WORDS(16384)) m0(rreset[0],cs[0],ck[0],ckn[0],dq[7:0],rwds[0]);
w955_ddr_model #(.OUTPUT_DELAY(5.5),.WORDS(16384)) m1(rreset[1],cs[1],ck[1],ckn[1],dq[15:8],rwds[1]);
reg[7:0] w0[0:262783],w1[0:131391];reg[31:0] expected[0:98303];
integer n0,k0,n1,k1,got=0,cycles=0,max_level0=0,max_level1=0,stalls=0;
reg[31:0] rng=32'h89131953,hold_data;reg hold_valid=0;
realtime begin_time,end_time;
always @(negedge clk)begin
 rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
 ready=rng[2:0]!=0; // downstream backpressure is included
end
always @(posedge clk)if(rst)begin
 if(fault)$fatal(1,"bridge fault words=%d cycles=%d sf=%b rf=%b qf=%b bf=%b pf=%b ov=%b",got,cycles,dut.sf,dut.rf,dut.qf,dut.bf,dut.pf,dut.overflow);
 if(hold_valid&&(!valid||data!==hold_data))$fatal(1,"stalled output changed");
 hold_valid=valid&&!ready;hold_data=data;
 if(valid&&!ready)stalls=stalls+1;
 if(valid&&ready)begin
  if(data!==expected[got])$fatal(1,"DDR payload mismatch word=%d got=%h expected=%h",got,data,expected[got]);
  if(offset!==(got/1024)*4096||last!==(got%1024==1023))$fatal(1,"page metadata");
  got=got+1;
 end
 cycles=cycles+1;if(cycles>700000)$fatal(1,"timeout %d",got);
 if(got==98304)begin
  end_time=$realtime;
  $display("PASS DDR wire-to-output bytes=%0d elapsed_ns=%0.3f stalls=%0d",got*4,end_time-begin_time,stalls);$finish;
 end
end
initial begin
 $readmemh("wire0.hex",w0);$readmemh("wire1.hex",w1);$readmemh("expected.hex",expected);
 #1;rst=0;#1;c0=1;c1=1;#100;rst=1;
 while(!init)@(negedge clk);#100;begin_time=$realtime;
 fork
  begin
   for(n0=0;n0<64;n0=n0+1)begin
    c0=0;
    for(k0=0;k0<4106;k0=k0+1)begin d0=w0[n0*4106+k0];#6.25;s0=1;#6.25;s0=0;end
    c0=1;#250;
   end
  end
  begin
   #37;
   for(n1=0;n1<32;n1=n1+1)begin
    c1=0;
    for(k1=0;k1<4106;k1=k1+1)begin
     d1=w1[n1*4106+k1]>>4;#6.25;s1=1;#6.25;s1=0;
     d1=w1[n1*4106+k1];#6.25;s1=1;#6.25;s1=0;
    end
    c1=1;#250;
   end
  end
 join
end
endmodule'''
        (out/'tb.sv').write_text(tb)
        names=['s3_async_fifo','s3_spi_rx','s3_page_guard','s3_page_reorder','s3_rx_page_store',
               's3_psram_burst','s3_psram_queue','s3_psram_phy','s3_psram_page_reader','s3_spi_memory_bridge']
        sources=[f'rtl/{name}.sv' for name in names]+['tests/fixtures/gowin_ddr_model.sv','tests/fixtures/w955_ddr_model.sv']
        c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),*[str(ROOT/s) for s in sources],str(out/'tb.sv')],text=True,capture_output=True)
        self.assertEqual(c.returncode,0,c.stderr)
        r=subprocess.run(['vvp','sim'],cwd=out,text=True,capture_output=True,timeout=90)
        (out/'simulation.log').write_text(r.stdout+r.stderr)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        report=dict(pages=pages,payload_bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
            SPI_MHz=80,core_MHz=99,die_output_delays_ns=[1,5.5],output=r.stdout.strip(),
            scope='two SPI ports through IDDR/ODDR and independent W955 pin model, with output stalls; no analog IO timing proof',
            receiver_adopted=False)
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':unittest.main()

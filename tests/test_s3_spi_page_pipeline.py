"""Concurrent 80-MHz Octal/Quad wires -> CDC -> reorder -> acknowledged memory."""
from pathlib import Path
import json
import random
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PipelineTest(unittest.TestCase):
    def test_wire_to_ordered_payload(self):
        out = ROOT/'build/s3-spi-page-pipeline'
        out.mkdir(parents=True, exist_ok=True)
        rng = random.Random(712906)
        wire = [bytearray(), bytearray()]
        expected = []
        for p in range(24):
            data = rng.randbytes(4096)
            port = int(p % 3 == 2)  # Octal : Quad payload split = 2 : 1
            wire[port].extend(bytes.fromhex('d7110011') + (p*4096).to_bytes(4, 'big') + b'\x10\x00' + data)
            expected.extend(int.from_bytes(data[i:i+4], 'little') for i in range(0, 4096, 4))
        for port in range(2):
            (out/f'wire{port}.hex').write_text(''.join(f'{x:02x}\n' for x in wire[port]))
        (out/'expected.hex').write_text(''.join(f'{x:08x}\n' for x in expected))
        (out/'tb.sv').write_text(r'''`timescale 1ns/1ps
module tb;
reg clk=0;always #5.050505 clk=~clk;
reg rst=1,s0=0,s1=0,c0=0,c1=0;reg[7:0] d0=0;reg[3:0] d1=0;
wire[35:0] t0,t1;wire[1:0] v,r,ov;
s3_spi_rx #(.LANES(8)) rx0(s0,c0,clk,rst,d0,v[0],r[0],t0,ov[0]);
s3_spi_rx #(.LANES(4)) rx1(s1,c1,clk,rst,d1,v[1],r[1],t1,ov[1]);
wire mv,mt,pv,fault;reg mr=0,av=0,at=0;wire[13:0] ma;wire[31:0] md,po;
wire[3:0] ps;reg retire=0;
s3_rx_page_store store(clk,rst,16'd17,v,r,t0,t1,|ov,mv,mr,ma,md,mt,av,at,pv,po,ps,retire,fault);
reg[7:0] w0[0:65695],w1[0:32847];reg[31:0] expected[0:24575],mem[0:16383];
reg[31:0] random_state=32'h35298137,wd;reg[13:0] wa;
integer n0,k0,n1,k1,got=0,cycles=0,idx=0;reg reading=0;
always @(negedge clk)begin
 random_state=random_state^(random_state<<13);
 random_state=random_state^(random_state>>17);random_state=random_state^(random_state<<5);
 mr=random_state[2:0]!=0;
end
// Pipelined backend: each write becomes visible at its acknowledgement edge.
always @(posedge clk)begin
 if(!rst)begin av<=0;at<=0;end
 else begin
  av<=mv&&mr;at<=mt;wa<=ma;wd<=md;
  if(av)mem[wa]<=wd;
 end
end
always @(posedge clk)if(rst)begin
 if(fault||ov)$fatal(1,"pipeline poisoned got=%0d",got);
 retire<=0;
 if(!reading&&!retire&&pv)begin
  if(po!==got*4)$fatal(1,"descriptor order %h expected %h",po,got*4);
  reading<=1;idx<=0;
 end else if(reading&&random_state[4:3]!=0)begin
  if(mem[{ps,10'b0}+idx]!==expected[got])$fatal(1,"payload word %0d",got);
  got=got+1;idx<=idx+1;
  if(idx==1023)begin retire<=1;reading<=0;end
 end
 cycles=cycles+1;if(cycles>400000)$fatal(1,"timeout words=%0d",got);
 if(got==24576)begin $display("PASS wire-to-memory ordered bytes=%0d",got*4);$finish;end
end
initial begin
 $readmemh("wire0.hex",w0);$readmemh("wire1.hex",w1);$readmemh("expected.hex",expected);
 #1;rst=0;#1;c0=1;c1=1;#100;rst=1;#100;
 fork
  begin
   for(n0=0;n0<16;n0=n0+1)begin
    c0=0;
    for(k0=0;k0<4106;k0=k0+1)begin d0=w0[n0*4106+k0];#6.25;s0=1;#6.25;s0=0;end
    c0=1;#250;
   end
  end
  begin
   #37;
   for(n1=0;n1<8;n1=n1+1)begin
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
endmodule''')
        sources = ['s3_async_fifo', 's3_spi_rx', 's3_page_guard', 's3_page_reorder', 's3_rx_page_store']
        c = subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(out/'sim')] +
            [str(ROOT/f'rtl/{name}.sv') for name in sources] + [str(out/'tb.sv')], text=True, capture_output=True)
        self.assertEqual(c.returncode, 0, c.stderr)
        r = subprocess.run(['vvp', 'sim'], cwd=out, text=True, capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        (out/'result.json').write_text(json.dumps(dict(pages=24, payload_bytes=24*4096,
            SPI_MHz=80, core_MHz=99, output=r.stdout.strip(),
            scope='complete two-wire RX/CDC/guard/store chain with behavioral acknowledged memory',
            physical_memory_included=False, receiver_adopted=False), indent=2)+'\n')


if __name__ == '__main__':
    unittest.main()

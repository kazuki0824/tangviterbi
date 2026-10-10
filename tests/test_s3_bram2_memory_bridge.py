"""Two native pages arriving out of order through Octal and LCD16."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TwoPageMemoryTest(unittest.TestCase):
    def test_reordered_pages_and_backpressure(self):
        self.run_pages(False)

    def test_pipelined_reordered_pages_and_backpressure(self):
        self.run_pages(True)

    def run_pages(self,pipeline):
        out = ROOT / ('build/s3-bram2-memory-test-pipe' if pipeline else 'build/s3-bram2-memory-test')
        out.mkdir(parents=True, exist_ok=True)
        word0 = [0x22000000 | n for n in range(1024)]
        word1 = [0x11000000 | n for n in range(1024)]
        header0 = bytes.fromhex('d7110001000000001000')
        (out / 'spi.hex').write_text(''.join(f'{b:02x}\n' for b in
            header0 + b''.join(w.to_bytes(4, 'little') for w in word0)))
        beats = [0xd711, 1, 0, 4096, 4096, 0, 0, 0]
        for word in word1:
            beats.extend((word & 65535, word >> 16))
        (out / 'lcd.hex').write_text(''.join(f'{w:04x}\n' for w in beats))
        (out / 'tb.sv').write_text('''`timescale 1ns/1ps
module BUFG(input wire I,output wire O);assign O=I;endmodule
module tb;
reg clk=0;always #5.050505 clk=~clk;
reg resetn=1,spi_clk=0,spi_cs=0,lcd_clk=0,lcd_cs=0,dc=0;
reg[7:0] spi_d=0;reg[15:0] lcd_d=0;
wire valid,last,fault;wire[31:0] data,offset;
wire [19:0] retired_sequence;
wire spi2_clock_global;
reg ready=1;
s3_bram2_memory_bridge dut(clk,resetn,16'd1,spi_clk,spi_cs,spi_d,
 lcd_clk,lcd_cs,dc,lcd_d,valid,ready,data,last,offset,fault,retired_sequence,spi2_clock_global);
reg[7:0] spi_bytes[0:4105];reg[15:0] lcd_beats[0:2055];
integer got=0,j,k;
reg[31:0] expected;reg[31:0] cycles=0;
always @(negedge clk)begin cycles=cycles+1;ready=(cycles%7)!=0;end
always @(posedge clk)if(resetn)begin
 if(fault)$fatal(1,"bridge fault after %0d words",got);
 if(valid&&ready)begin
  expected=(got<1024?32'h22000000|(got&1023):32'h11000000|(got&1023));
  if(got>=2048||data!==expected||offset!==(got<1024?32'd0:32'd4096)||
     last!==(got%1024==1023))
   $fatal(1,"word %0d data=%h expected=%h offset=%d last=%b",got,data,expected,offset,last);
  got=got+1;
 end
end
initial begin
 $readmemh("spi.hex",spi_bytes);$readmemh("lcd.hex",lcd_beats);
 #1;resetn=0;#1;spi_cs=1;lcd_cs=1;#38;resetn=1;#100;
 // The later page reaches the reorder store before the earlier page.
 lcd_cs=0;
 for(j=0;j<2056;j=j+1)begin
  dc=j>=8;lcd_d=lcd_beats[j];#12.5;lcd_clk=1;#12.5;lcd_clk=0;
 end
 lcd_cs=1;#100;
 spi_cs=0;
 for(j=0;j<4106;j=j+1)begin
  for(k=0;k<8;k=k+8)begin
   spi_d=spi_bytes[j];#6.25;spi_clk=1;#6.25;spi_clk=0;
  end
 end
 spi_cs=1;#100000;
 if(got!=2048)$fatal(1,"missing words=%0d",got);
 $display("PASS 2 x 4096 native bytes, reordered, no data loss");$finish;
end
endmodule
''')
        if pipeline:
            p=out/'tb.sv'
            p.write_text(p.read_text().replace('s3_bram2_memory_bridge dut',
                         's3_bram2_memory_bridge #(.PIPE_WINDOW(1)) dut'))
        sources = [ROOT / ('rtl/' + s + '.sv') for s in (
            's3_async_fifo', 's3_spi_rx', 's3_lcd16_rx', 's3_page_guard',
            's3_page_reorder', 's3_rx_page_store', 's3_bram2_memory_bridge')]
        cmd = ['iverilog', '-g2012', '-s', 'tb', '-o', str(out / 'sim')]
        p = subprocess.run(cmd + list(map(str, sources)) + [str(out / 'tb.sv')],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        p = subprocess.run(['vvp', 'sim'], cwd=out, capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn('PASS', p.stdout)


if __name__ == '__main__':
    unittest.main()

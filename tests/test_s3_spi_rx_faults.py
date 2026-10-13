"""Overflow/overlong writes poison RX even after CS rises and SCK stops."""
from pathlib import Path
import json
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FaultTest(unittest.TestCase):
    def test_latched_faults(self):
        results = []
        for lanes in (4, 8):
            out = ROOT / f'build/s3-spi-rx-faults/{lanes}'
            out.mkdir(parents=True, exist_ok=True)
            tb = r'''`timescale 1ns/1ps
module tb;
localparam L=LANES;
reg clk=0;always #5.050505 clk=~clk;
reg sck=0,cs=0,rst=1,ready=1;reg[L-1:0] dq=0;
wire valid,overflow;wire[35:0] token;
s3_spi_rx #(.LANES(L)) dut(sck,cs,clk,rst,dq,valid,ready,token,overflow);
task octet(input[7:0] b);integer k;begin
 for(k=8-L;k>=0;k=k-L)begin dq=b>>k;#6.25;sck=1;#6.25;sck=0;end
end endtask
task reset;begin cs=1;rst=0;#100;rst=1;#100;if(overflow)$fatal(1,"reset");end endtask
task header;begin cs=0;octet('hd7);octet('h11);octet(0);octet(1);
 repeat(4)octet(0);octet('h10);octet(0);end endtask
integer i;
initial begin
 #1;reset();header();for(i=0;i<4096;i=i+1)octet(i);
 #1;if(overflow)$fatal(1,"normal page overflow");
 octet('h5a);cs=1;#100;
 if(!overflow)$fatal(1,"overlong write not detected without more SCK");
 #1000;if(!overflow)$fatal(1,"CS cleared sticky fault");
 reset();ready=0;header();repeat(512)octet('h95);cs=1;#100;
 if(!overflow)$fatal(1,"FIFO overflow missing");
 ready=1;#10000;if(!overflow)$fatal(1,"drain cleared sticky fault");
 reset();$display("PASS overlong write and FIFO exhaustion");$finish;
end
endmodule'''.replace('LANES;', f'{lanes};')
            (out/'tb.sv').write_text(tb)
            c = subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(out/'sim'),
                str(ROOT/'rtl/s3_async_fifo.sv'), str(ROOT/'rtl/s3_spi_rx.sv'), str(out/'tb.sv')],
                text=True, capture_output=True)
            self.assertEqual(c.returncode, 0, c.stderr)
            r = subprocess.run(['vvp', 'sim'], cwd=out, text=True, capture_output=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
            results.append(dict(lanes=lanes, fault_cases=2, output=r.stdout.strip()))
        (ROOT/'build/s3-spi-rx-faults/result.json').write_text(json.dumps(
            dict(cases=results, receiver_adopted=False), indent=2)+'\n')


if __name__ == '__main__':
    unittest.main()

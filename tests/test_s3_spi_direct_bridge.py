"""Independent native IQ oracle through physical SPI, page order and BSRAM."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DirectBridgeTest(unittest.TestCase):
    def test_native_samples_order_stalls_read_commands_and_poison(self):
        self.run_case(False)

    def test_three_outstanding_pages_with_sampled_Gray_credit(self):
        self.run_case(True)

    def run_case(self, gray_credit):
        out = ROOT / ("build/s3-direct-bridge-credit" if gray_credit else "build/s3-direct-bridge-test")
        out.mkdir(parents=True, exist_ok=True)
        samples = [(n * 65537 + 12345) & 0xfffff for n in range(65536)]
        raw = b"".join((a | (b << 20)).to_bytes(5, "little") for a, b in zip(samples[::2], samples[1::2]))
        self.assertEqual(len(raw), 40 * 4096)
        frames = [[], []]
        for page in range(40):
            port = 0 if page % 3 != 2 else 1
            frames[port].append((page, bytes.fromhex("d7110011") + (page * 4096).to_bytes(4, "big") + bytes.fromhex("1000") + raw[page * 4096:(page + 1) * 4096]))
        for port in (0, 1):
            (out / f"port{port}.hex").write_text("".join(f"{b:02x}\n" for _, frame in frames[port] for b in frame))
            (out / f"page{port}.hex").write_text("".join(f"{p:08x}\n" for p, _ in frames[port]))
        (out / "expected.hex").write_text("".join(f"{s:05x}\n" for s in samples))
        tb = r'''`timescale 1ns/1ps
module tb;
reg clk=0;always #5.555556 clk=~clk;
reg resetn=1,s2=0,s3=0,cs2=1,cs3=1;reg[7:0] d2=0;reg[3:0] d3=0;
wire ov,ready,last,fault;wire[31:0] data,offset;reg sink_ready=0;
wire iqv;wire[9:0] oi,oq;
s3_spi_direct_bridge dut(clk,resetn,16'd17,s2,cs2,d2,s3,cs3,d3,ov,ready,data,last,offset,fault);
s3_iq10_unpack unpack(clk,resetn,ov,ready,data,iqv,sink_ready,oi,oq);
reg[7:0] wire0[0:N0*4106-1],wire1[0:N1*4106-1];
reg[31:0] pages0[0:N0-1],pages1[0:N1-1];reg[19:0] expected[0:65535];
integer retired=0,words=0,received=0,cycles=0,p0,i0,p1,i1;
reg run=0,stalled=0;reg[31:0] held;reg held_last;reg[31:0] held_offset;
reg[31:0] rng=32'hba321fe4;
always @(negedge clk)begin
 rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);sink_ready=rng[3:0]!=0;
end
always @(posedge clk)if(resetn&&run)begin
 if(stalled&&(!ov||data!==held||last!==held_last||offset!==held_offset))$fatal(1,"output changed while stalled");
 stalled=ov&&!ready;held=data;held_last=last;held_offset=offset;
 if(ov&&ready)begin
  if(offset!==4096*retired || last!==(words%1024==1023))$fatal(1,"page identity/last mismatch");
  words=words+1;if(last)retired=retired+1;
 end
 if(iqv&&sink_ready)begin
  if(received>=65536 || {oq,oi}!==expected[received])$fatal(1,"native sample mismatch %0d",received);
  received=received+1;
 end
 cycles=cycles+1;if(cycles>500000 || fault)$fatal(1,"normal-path fault/deadlock words=%0d samples=%0d",words,received);
end
task octet0(input[7:0] b);begin d2=b;#6.25;s2=1;#6.25;s2=0;end endtask
task octet1(input[7:0] b);begin d3=b[7:4];#6.25;s3=1;#6.25;s3=0;d3=b[3:0];#6.25;s3=1;#6.25;s3=0;end endtask
initial begin
 #1;resetn=0;
 // CS is already high at power-up: clock once under reset to initialize
 // the frame parser in event-driven simulation as well as the async FIFOs.
 #7;s2=1;s3=1;#7;s2=0;s3=0;
 $readmemh("port0.hex",wire0);$readmemh("port1.hex",wire1);
 $readmemh("page0.hex",pages0);$readmemh("page1.hex",pages1);$readmemh("expected.hex",expected);
 repeat(4)@(negedge clk);resetn=1;run=1;
 fork
  begin
   for(p0=0;p0<N0;p0=p0+1)begin
    // Testbench credit: no new page outside the four-slot receive window.
    while(pages0[p0]>=retired+4)@(negedge clk);
    cs2=0;for(i0=0;i0<4106;i0=i0+1)octet0(wire0[p0*4106+i0]);cs2=1;
    if(p0%3==2)#20000;else #250;
   end
  end
  begin
   #137;
   for(p1=0;p1<N1;p1=p1+1)begin
    while(pages1[p1]>=retired+4)@(negedge clk);
    cs3=0;for(i1=0;i1<4106;i1=i1+1)octet1(wire1[p1*4106+i1]);cs3=1;#20000;
   end
  end
 join
 while(received<65536)@(negedge clk);
 if(words!=40960||retired!=40)$fatal(1,"payload accounting");
 run=0;repeat(10)@(negedge clk);
 if(ov||iqv||fault)$fatal(1,"unexpected trailing payload");
 // A D71B read command is not an incoming RF write and must not poison RX.
 cs2=0;octet0(8'hd7);octet0(8'h1b);for(i0=0;i0<4104;i0=i0+1)octet0(0);cs2=1;
 repeat(30)@(negedge clk);if(fault||ov)$fatal(1,"read command treated as RF");
 // Wrong epoch: never publish a stale page; mask outputs until reset.
 cs2=0;octet0(8'hd7);octet0(8'h11);octet0(0);octet0(8'h12);cs2=1;
 repeat(40)@(negedge clk);if(!fault||ov)$fatal(1,"bad epoch not poisoned");
 repeat(100)@(negedge clk);if(!fault||ov)$fatal(1,"fault not sticky");
 resetn=0;repeat(4)@(negedge clk);resetn=1;repeat(10)@(negedge clk);
 if(fault||ov)$fatal(1,"reset published stale memory");
 $display("PASS 65536 native samples, 40 pages, independent physical ports, stalls, read-ignore, epoch poison");$finish;
end
endmodule'''.replace("N0", str(len(frames[0]))).replace("N1", str(len(frames[1])))
        if gray_credit:
            tb=tb.replace('s3_spi_direct_bridge dut','s3_spi_direct_bridge #(.WINDOW_PIPELINE(1)) dut')
            tb=tb.replace('integer retired=0,', """wire[1:0] gray;
s3_rf_credit credit(clk,resetn,ov&&ready&&last,gray);
integer host_retired=0,previous_binary=0,poll_cycles=0;
integer retired=0,""")
            tb=tb.replace('always @(negedge clk)begin', """always @(negedge clk)begin
 if(!resetn)begin host_retired=0;previous_binary=0;poll_cycles=0;end
 else if(poll_cycles==899)begin host_retired=host_retired+(((gray^(gray>>1))-previous_binary)&3);previous_binary=gray^(gray>>1);poll_cycles=0;end
 else poll_cycles=poll_cycles+1;""")
            tb=tb.replace('>=retired+4','>=host_retired+3')
        (out / "tb.sv").write_text(tb)
        sources = ["s3_async_fifo.sv", "s3_spi_rx.sv", "s3_page_guard.sv", "s3_page_reorder.sv",
                   "s3_rx_page_store.sv", "s3_spi_direct_bridge.sv", "s3_iq10_unpack.sv", "s3_rf_credit.sv"]
        c = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(out / "sim"),
                            *[str(ROOT / "rtl" / s) for s in sources], str(out / "tb.sv")], capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stderr)
        r = subprocess.run(["vvp", "sim"], cwd=out, capture_output=True, text=True, timeout=60)
        (out / "simulation.log").write_text(r.stdout + r.stderr)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PASS 65536", r.stdout)


if __name__ == "__main__":
    unittest.main()

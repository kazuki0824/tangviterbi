"""FPGA-consumption credit, not DMA completion; native page ownership."""
import ctypes as C
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]


class Credit(C.Structure):
    _fields_=[('next',C.c_uint32),('retired',C.c_uint32),('epoch',C.c_uint16),('window',C.c_uint8),
              ('synced',C.c_bool),('poisoned',C.c_bool)]


def response(epoch,frontier,flags=0,window=2):
    value=(0xc7a1<<48)|(epoch<<32)|(frontier<<12)|(window<<8)|flags
    raw=value.to_bytes(8,'big')
    return raw+bytes(x^255 for x in raw)


class PageCreditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=ROOT/'build/s3-page-credit-test';cls.out.mkdir(parents=True,exist_ok=True)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',
                        '-I',str(ROOT/'experiments'),str(ROOT/'experiments/s3_page_credit.c'),
                        '-o',str(cls.out/'credit.so')],check=True,capture_output=True)
        cls.lib=C.CDLL(str(cls.out/'credit.so'))
        cls.lib.s3_credit_init.argtypes=[C.POINTER(Credit),C.c_uint,C.c_uint32]
        cls.lib.s3_credit_init_window.argtypes=[C.POINTER(Credit),C.c_uint,C.c_uint32,C.c_uint]
        cls.lib.s3_credit_status.argtypes=[C.POINTER(Credit),C.POINTER(C.c_uint8)]
        cls.lib.s3_credit_reserve.argtypes=[C.POINTER(Credit),C.c_uint,C.POINTER(C.c_uint32)]

    def status(self,c,data):
        return self.lib.s3_credit_status(C.byref(c),(C.c_uint8*16).from_buffer_copy(data))

    def test_consumption_window_and_wrap(self):
        c=Credit();first=C.c_uint32()
        self.assertEqual(self.lib.s3_credit_init(C.byref(c),7,0xffffe),0)
        self.assertEqual(self.lib.s3_credit_reserve(C.byref(c),1,C.byref(first)),1)
        self.assertEqual(self.status(c,response(7,0xffffe)),0)
        self.assertEqual(self.lib.s3_credit_reserve(C.byref(c),2,C.byref(first)),0)
        self.assertEqual(first.value,0xffffe)
        # Reaping both DMA transfers changes no receiver credit.
        self.assertEqual(self.lib.s3_credit_reserve(C.byref(c),1,C.byref(first)),1)
        self.assertEqual(self.status(c,response(7,0xffffe)),0)
        self.assertEqual(self.lib.s3_credit_reserve(C.byref(c),1,C.byref(first)),1)
        for n in range(4096):
            retired=(0xfffff+n)&0xfffff
            self.assertEqual(self.status(c,response(7,retired)),0)
            self.assertEqual(self.lib.s3_credit_reserve(C.byref(c),1,C.byref(first)),0)
            self.assertEqual(first.value,(retired+1)&0xfffff)
            self.assertEqual(self.lib.s3_credit_reserve(C.byref(c),1,C.byref(first)),1)

    def test_advertised_larger_windows_and_wrap(self):
        for window in (4,8):
            c=Credit();first=C.c_uint32()
            self.assertEqual(self.lib.s3_credit_init_window(C.byref(c),7,0xffffc,window),0)
            self.assertEqual(self.status(c,response(7,0xffffc,window=window)),0)
            self.assertEqual(self.lib.s3_credit_reserve(C.byref(c),window,C.byref(first)),0)
            self.assertEqual(self.lib.s3_credit_reserve(C.byref(c),1,C.byref(first)),1)
            self.assertEqual(self.status(c,response(7,0,window=window)),0)
            self.assertEqual(self.lib.s3_credit_reserve(C.byref(c),4,C.byref(first)),0)
            self.assertEqual(first.value,window-4)
            self.assertEqual(self.status(c,response(7,0,window=2)),3)

    def test_invalid_or_stale_snapshot_poison(self):
        variants=[response(8,0),response(7,1),response(7,0,1),response(7,0,0,3)]
        good=response(7,0)
        variants += [good[:i]+bytes([good[i]^1])+good[i+1:] for i in range(16)]
        for data in variants:
            with self.subTest(data=data.hex()):
                c=Credit();first=C.c_uint32();self.lib.s3_credit_init(C.byref(c),7,0)
                self.assertEqual(self.status(c,data),3)
                self.assertTrue(c.poisoned)
                self.assertEqual(self.lib.s3_credit_reserve(C.byref(c),1,C.byref(first)),3)

    def test_wire_snapshot_and_read_not_in_rx(self):
        tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0;always #5.555555 clk=~clk;
reg rst=1,sck=0,cs=0;reg[7:0] din=0;
reg[19:0] frontier=20'hffffe;reg bad=0;
wire[7:0] dout;wire oe,fault,rv,overflow;wire[35:0] token;
s3_spi_page_status dut(clk,rst,16'd7,frontier,bad,sck,cs,din,dout,oe,fault);
s3_spi_rx #(.LANES(8),.FIFO_AW(7),.IGNORE_STATUS_READ(1)) rx(
 sck,cs,clk,rst,din,rv,1'b1,token,overflow);
always @(posedge clk)if(rst&&(rv||overflow))$fatal(1,"status entered write FIFO");
task beat(input[7:0] b);begin din=b;#6.25;sck=1;#6.25;sck=0;end endtask
task query(input[15:0] ep);integer j;begin
 cs=0;beat(8'hd7);beat(8'h1c);beat(ep[15:8]);beat(ep[7:0]);
 repeat(4)beat(0);beat(0);beat(16);repeat(16)beat(0);
 $write("STATUS ");
 for(j=0;j<16;j=j+1)begin
  #6.25;sck=1;
  if(oe!==1'b1)$fatal(1,"response not driven at byte %0d",j);
  $write("%02h",dout);
  if(j==3)frontier=frontier+1'b1;
  #6.25;sck=0;
 end
 $write("\n");cs=1;#100;
end endtask
initial begin
 #1;rst=0;#1;cs=1;#49;rst=1;#100;query(7);query(7);
 bad=1;#100;query(7);
 if(fault)$fatal(1,"valid queries poisoned endpoint");
 // No response for a stale epoch. A fresh reset is required afterwards.
 cs=0;beat(8'hd7);beat(8'h1c);beat(0);beat(6);
 repeat(4)beat(0);beat(0);beat(16);repeat(17)beat(0);
 if(oe||!fault)$fatal(1,"stale epoch not rejected");
 cs=1;#100;$display("PASS");$finish;
end
endmodule
'''
        out=self.out/'wire';out.mkdir(exist_ok=True);(out/'tb.sv').write_text(tb)
        p=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),
                         str(ROOT/'rtl/s3_spi_page_status.sv'),str(ROOT/'rtl/s3_spi_rx.sv'),
                         str(ROOT/'rtl/s3_async_fifo.sv'),str(out/'tb.sv')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        p=subprocess.run(['vvp','sim'],cwd=out,capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        packets=[bytes.fromhex(x.split()[1]) for x in p.stdout.splitlines() if x.startswith('STATUS ')]
        self.assertEqual(packets,[response(7,0xffffe),response(7,0xfffff),response(7,0,1)])
        self.assertIn('PASS',p.stdout)


if __name__=='__main__':unittest.main()

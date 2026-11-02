"""Two independent outer RS(204,188) codewords through one actual decoder and two TS sinks."""
import subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments"))
from s3_rs_isdb import source
from check_isdb_rs import encode
class SharedRSToDualTS(unittest.TestCase):
 def test_shared_rs_to_two_ts(self):
  out=ROOT/"build/shared-rs-dual-ts";out.mkdir(parents=True,exist_ok=True)
  payloads=[[0x47]+[(n*17+3)&255 for n in range(187)],
            [0x47]+[(n*29+11)&255 for n in range(187)]]
  for i,payload in enumerate(payloads):
   (out/f"cw{i}.hex").write_text("\n".join(f"{x:02x}" for x in encode(payload))+"\n")
   (out/f"expected{i}.hex").write_text("\n".join(f"{x:02x}" for x in payload)+"\n")
  generated=out/"rs_isdb_verified.sv";generated.write_text(source(True,True))
  tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0;always #5 clk=~clk;
reg[7:0] cw0[0:203],cw1[0:203],expect0[0:187],expect1[0:187];
integer tx0=0,tx1=0,rx0=0,rx1=0;
reg[7:0]byte0=0,byte1=0;
wire[1:0] in_ready,tc,td,tv,fault;
wire[1:0] in_valid={tx1<204,tx0<204};
wire[15:0]in_byte={cw1[tx1<204?tx1:203],cw0[tx0<204?tx0:203]};
shared_rs2_dual_ts dut(clk,rst,in_valid,in_ready,in_byte,tc,td,tv,fault);
always @(posedge clk)if(rst)begin
 if(in_valid[0]&&in_ready[0])tx0<=tx0+1;
 if(in_valid[1]&&in_ready[1])tx1<=tx1+1;
 if(fault)$fatal(1,"unexpected RS/TS fault");
end
always @(posedge tc[0])if(tv[0])begin
 byte0={byte0[6:0],td[0]};rx0=rx0+1;
 if(rx0%8==0&&byte0!==expect0[rx0/8-1])
  $fatal(1,"T RS->TS byte %0d got %h exp %h",rx0/8-1,byte0,expect0[rx0/8-1]);
end
always @(posedge tc[1])if(tv[1])begin
 byte1={byte1[6:0],td[1]};rx1=rx1+1;
 if(rx1%8==0&&byte1!==expect1[rx1/8-1])
  $fatal(1,"S RS->TS byte %0d got %h exp %h",rx1/8-1,byte1,expect1[rx1/8-1]);
end
initial begin
 $readmemh("cw0.hex",cw0);$readmemh("cw1.hex",cw1);
 $readmemh("expected0.hex",expect0);$readmemh("expected1.hex",expect1);
 #1;rst=0;repeat(4)@(negedge clk);rst=1;
 wait(rx0==188*8&&rx1==188*8);
 if(tx0!=204||tx1!=204)$fatal(1,"input loss");
 $display("PASS two RS codewords shared one RS decoder and two independent TS sinks");
 $finish;
end
initial begin #3000000;$fatal(1,"RS arbitration timeout");end
endmodule
'''
  (out/"tb.sv").write_text(tb)
  sources=[generated,ROOT/"rtl/isdb_serial_ts_sink.sv",ROOT/"rtl/shared_rs2_dual_ts.sv",out/"tb.sv"]
  p=subprocess.run(["iverilog","-g2012","-s","tb","-o",str(out/"sim"),*[str(x) for x in sources]],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
  r=subprocess.run(["vvp","sim"],cwd=out,capture_output=True,text=True,timeout=90)
  (out/"run.log").write_text(r.stdout+r.stderr)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  self.assertIn("PASS two RS codewords",r.stdout)
if __name__=="__main__":unittest.main()

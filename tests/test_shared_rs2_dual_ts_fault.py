"""Fail-closed test: one bad TS sync codeword cannot disable the other stream."""
import subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments"))
from s3_rs_isdb import source
from check_isdb_rs import encode
class RSIsolationTest(unittest.TestCase):
 def test_bad_t_sync_does_not_poison_s(self):
  out=ROOT/"build/shared-rs-ts-fault";out.mkdir(parents=True,exist_ok=True)
  good=[0x47]+[(i*11+13)&255 for i in range(187)]
  (out/"cw0.hex").write_text("\n".join("00" for _ in range(204))+"\n")
  (out/"cw1.hex").write_text("\n".join(f"{x:02x}" for x in encode(good))+"\n")
  (out/"expected.hex").write_text("\n".join(f"{x:02x}" for x in good)+"\n")
  rs=out/"rs_isdb_verified.sv";rs.write_text(source(True,True))
  tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0;always #5 clk=~clk;
reg[7:0]cw0[0:203],cw1[0:203],want[0:187];
integer tx0=0,tx1=0,rx1=0;
reg[7:0]captured=0;
wire[1:0]rdy,tc,td,tv,fault;
wire[1:0]v={tx1<204,tx0<204};
wire[15:0]data={cw1[tx1<204?tx1:203],cw0[tx0<204?tx0:203]};
shared_rs2_dual_ts dut(clk,rst,v,rdy,data,tc,td,tv,fault);
always @(posedge clk)if(rst)begin
 if(v[0]&&rdy[0])tx0<=tx0+1;
 if(v[1]&&rdy[1])tx1<=tx1+1;
 if(fault[1])$fatal(1,"healthy S faulted");
end
always @(posedge tc[0])if(tv[0]&&fault[0])$fatal(1,"bad T output after fault");
always @(posedge tc[1])if(tv[1])begin
 captured={captured[6:0],td[1]};rx1=rx1+1;
 if(rx1%8==0&&captured!==want[rx1/8-1])$fatal(1,"S payload changed");
end
initial begin
 $readmemh("cw0.hex",cw0);$readmemh("cw1.hex",cw1);$readmemh("expected.hex",want);
 #1;rst=0;repeat(4)@(negedge clk);rst=1;
 wait(rx1==188*8);
 if(!fault[0]||fault[1]||tx1!=204)$fatal(1,"fault isolation failed");
 $display("PASS bad T TS sync fail-closed; S RS/TS continues independently");
 $finish;
end
initial begin #3000000;$fatal(1,"fault isolation timeout");end
endmodule
'''
  (out/"tb.sv").write_text(tb)
  p=subprocess.run(["iverilog","-g2012","-s","tb","-o",str(out/"sim"),str(rs),
       str(ROOT/"rtl/isdb_serial_ts_sink.sv"),str(ROOT/"rtl/shared_rs2_dual_ts.sv"),str(out/"tb.sv")],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
  result=subprocess.run(["vvp","sim"],cwd=out,capture_output=True,text=True,timeout=90)
  (out/"run.log").write_text(result.stdout+result.stderr)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  self.assertIn("PASS bad T TS sync",result.stdout)
if __name__=="__main__":unittest.main()

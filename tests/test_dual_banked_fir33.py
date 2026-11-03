"""Reference exact signed complex 33-tap convolution, two FPGA workloads."""
import random,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
N=64
def sign_bits(value,bits):return value & ((1<<bits)-1)
class BankedDualFIRTest(unittest.TestCase):
 def test_two_fir_references(self):
  rng=random.Random(20261102)
  out=ROOT/"build/dual-banked-fir33";out.mkdir(parents=True,exist_ok=True)
  coeff=[rng.randrange(-256,256) for _ in range(33)]
  data={}
  for lane in (0,1):
   a=[rng.randrange(-512,512) for _ in range(N)]
   b=[rng.randrange(-512,512) for _ in range(N)]
   data[lane]=(a,b)
   for kind,seq,width in (
      ("i",a,10),("q",b,10),
      ("want_i",[sum(coeff[k]*a[n-k] for k in range(33) if n>=k) for n in range(N)],32),
      ("want_q",[sum(coeff[k]*b[n-k] for k in range(33) if n>=k) for n in range(N)],32)):
    (out/f"{kind}{lane}.hex").write_text("\n".join(f"{sign_bits(v,width):0{(width+3)//4}x}" for v in seq)+"\n")
  (out/"coeff.hex").write_text("\n".join(f"{sign_bits(v,16):04x}" for v in coeff)+"\n")
  tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0;always #5 clk=~clk;
reg signed [15:0]coeff[0:32];
reg signed [9:0] i0[0:63],q0[0:63],i1[0:63],q1[0:63];
reg signed [31:0]want_i0[0:63],want_q0[0:63],want_i1[0:63],want_q1[0:63];
integer tx0=0,tx1=0,rx0=0,rx1=0,cycle=0,ci=0;
reg configuring=1;
wire[1:0] ir,ov,cr;
wire signed [63:0]oi,oq;
reg[1:0] iv=0,orr=2'b11,cv=0;
reg[11:0]ca=0;reg signed [31:0]coeff_word=0;
wire signed [19:0]in_i={i1[tx1<64?tx1:63],i0[tx0<64?tx0:63]};
wire signed [19:0]in_q={q1[tx1<64?tx1:63],q0[tx0<64?tx0:63]};
dual_isdb_complex_fir33_banked dut(
 .clk(clk),.resetn(rst),.in_valid(iv),.in_ready(ir),.in_i(in_i),.in_q(in_q),
 .out_valid(ov),.out_ready(orr),.out_i(oi),.out_q(oq),
 .coeff_valid(cv),.coeff_ready(cr),.coeff_addr(ca),.coeff_value(coeff_word)
);
always @(negedge clk)if(rst)begin
 if(configuring)begin
  cv=2'b11;iv=0;
  ca={ci[5:0],ci[5:0]};
  coeff_word={coeff[ci],coeff[ci]};
 end else begin
  cv=0;
  iv[0]=tx0<64 && cycle%13!=7;
  iv[1]=tx1<64 && cycle%17!=11;
  orr[0]=cycle%9!=2;orr[1]=cycle%11!=4;
 end
end
always @(posedge clk)if(rst)begin
 cycle<=cycle+1;
 if(configuring)begin
  if(cv==2'b11 && cr==2'b11)begin
   if(ci==32)begin configuring<=0;cv<=0;end
   else ci<=ci+1;
  end
 end else begin
  if(iv[0]&&ir[0])tx0<=tx0+1;
  if(iv[1]&&ir[1])tx1<=tx1+1;
  if(ov[0]&&orr[0])begin
   if(rx0>=64||oi[31:0]!==want_i0[rx0]||oq[31:0]!==want_q0[rx0])
    $fatal(1,"T FIR mismatched n=%0d got=%0d/%0d expected=%0d/%0d",rx0,oi[31:0],oq[31:0],want_i0[rx0],want_q0[rx0]);
   rx0<=rx0+1;
  end
  if(ov[1]&&orr[1])begin
   if(rx1>=64||oi[63:32]!==want_i1[rx1]||oq[63:32]!==want_q1[rx1])
    $fatal(1,"S FIR mismatched n=%0d got=%0d/%0d expected=%0d/%0d",rx1,oi[63:32],oq[63:32],want_i1[rx1],want_q1[rx1]);
   rx1<=rx1+1;
  end
  if(rx0==64 && rx1==64)begin
   $display("PASS parallel T PAR4 and S PAR11 33tap complex FIR bit-exact independent reference");$finish;
  end
 end
 if(cycle>4000)$fatal(1,"FIR deadlock timeout");
end
initial begin
 $readmemh("coeff.hex",coeff);
 $readmemh("i0.hex",i0);$readmemh("q0.hex",q0);
 $readmemh("i1.hex",i1);$readmemh("q1.hex",q1);
 $readmemh("want_i0.hex",want_i0);$readmemh("want_q0.hex",want_q0);
 $readmemh("want_i1.hex",want_i1);$readmemh("want_q1.hex",want_q1);
 #1;rst=0;repeat(4)@(negedge clk);rst=1;
end
endmodule
'''
  (out/"tb.sv").write_text(tb)
  compile=subprocess.run(["iverilog","-g2012","-s","tb","-o",str(out/"sim"),
                           str(ROOT/"experiments/isdb_complex_fir33_banked.sv"),str(out/"tb.sv")],capture_output=True,text=True)
  self.assertEqual(compile.returncode,0,compile.stderr)
  result=subprocess.run(["vvp","sim"],cwd=out,capture_output=True,text=True,timeout=45)
  (out/"run.log").write_text(result.stdout+result.stderr)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  self.assertIn("PASS parallel T PAR4 and S PAR11",result.stdout)
if __name__=="__main__":unittest.main()

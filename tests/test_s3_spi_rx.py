"""Real 80-MHz SPI waveforms through independent 99-MHz FIFO/consumer clock."""
from pathlib import Path
import json,random,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class SPIRxTest(unittest.TestCase):
    def test_octal_and_quad_clock_crossing(self):
        results=[]
        for lanes in (4,8):
            out=ROOT/f'build/s3-spi-rx/{lanes}';out.mkdir(parents=True,exist_ok=True)
            rng=random.Random(100+lanes);raw=bytearray();expected=[]
            for p in range(6):
                cmd=0xd711 if p%2==0 else 0xd712;epoch=17
                header=cmd.to_bytes(2,'big')+epoch.to_bytes(2,'big')+(p*4096).to_bytes(4,'big')+(4096).to_bytes(2,'big')
                payload=rng.randbytes(4096);raw.extend(header+payload)
                expected.extend([(1<<32)|(cmd<<16)|epoch,(2<<32)|p*4096,(3<<32)|4096])
                expected.extend(((8<<32) if i==4092 else 0)|int.from_bytes(payload[i:i+4],'little') for i in range(0,4096,4))
            (out/'wire.hex').write_text(''.join(f'{v:02x}\n' for v in raw))
            (out/'tokens.hex').write_text(''.join(f'{v:09x}\n' for v in expected))
            tb='''`timescale 1ns/1ps
module tb;
reg clk=0;always #5.050505 clk=~clk;
reg sck=0,cs=0,rst=1,ready=1;reg [LANES-1:0] dq=0;
wire valid,overflow;wire [35:0] token;
s3_spi_rx #(.LANES(LANES)) dut(sck,cs,clk,rst,dq,valid,ready,token,overflow);
reg [7:0] data[0:24635];reg [35:0] want[0:6161];
integer j,k,p,got=0,c=0; reg [31:0] rng=32'hb5192746;
reg stalled=0;reg [35:0] hold;
always @(negedge clk) begin
 rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
 ready=rng[2:0]!=0; // stalls without exceeding FIFO depth
end
always @(posedge clk) if(rst) begin
 if(overflow) $fatal(1,"overflow");
 if(stalled && (!valid || token!==hold)) $fatal(1,"stall instability");
 stalled=valid&&!ready;hold=token;
 if(valid&&ready) begin
  if(got>=6162 || token!==want[got]) $fatal(1,"token %0d got %h expected %h",got,token,want[got]);
  got=got+1;
 end
end
initial begin
 $readmemh("wire.hex",data);$readmemh("tokens.hex",want);
 #1;rst=0;#1;cs=1;#38;rst=1;#100;
 for(p=0;p<6;p=p+1) begin
  cs=0;
  for(j=0;j<4106;j=j+1) begin
   for(k=8-LANES;k>=0;k=k-LANES) begin
    dq=data[p*4106+j]>>k;#6.25;sck=1;#6.25;sck=0;
   end
  end
  cs=1;#250;
 end
 #1000;
 if(got!=6162) $fatal(1,"missing final token %0d",got);
 $display("PASS lanes=LANES tokens=%0d",got);$finish;
end
endmodule
'''.replace('LANES',str(lanes)).replace('.'+str(lanes)+'(','.LANES(')
            (out/'tb.sv').write_text(tb)
            c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(ROOT/'rtl/s3_async_fifo.sv'),str(ROOT/'rtl/s3_spi_rx.sv'),str(out/'tb.sv')],text=True,capture_output=True)
            self.assertEqual(c.returncode,0,c.stderr)
            r=subprocess.run(['vvp','sim'],cwd=out,text=True,capture_output=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            results.append(dict(lanes=lanes,SPI_MHz=80,core_MHz=99,payload_bytes=6*4096,tokens=len(expected),output=r.stdout.strip()))
        (ROOT/'build/s3-spi-rx/result.json').write_text(json.dumps(dict(cases=results,scope='RX wire framing and CDC only; no PSRAM, reorder, status or read endpoint',receiver_adopted=False),indent=2)+'\n')
if __name__=='__main__':unittest.main()

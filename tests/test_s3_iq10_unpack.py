"""Independent bitstream oracle across 4-KiB page edges, stalls and resets."""
from pathlib import Path
import json, random, subprocess, unittest
ROOT=Path(__file__).resolve().parents[1]
class IQUnpackTest(unittest.TestCase):
    def test_all_native_values_and_boundaries(self):
        out=ROOT/'build/s3-unpack';out.mkdir(parents=True,exist_ok=True)
        # Each native 20-bit pattern occurs once, permuted by odd multiplication.
        # Use integer serialization, independent of the C packer and RTL.
        epochs=[[(i*65537+12345)&0xfffff for i in range(1<<20)],
                [0,0xfffff,0x80000,0x00200]*64]
        expected=[];words=[]
        for values in epochs:
            raw=bytearray()
            for a,b in zip(values[::2],values[1::2]):raw.extend((a|(b<<20)).to_bytes(5,'little'))
            words.append([int.from_bytes(raw[i:i+4],'little') for i in range(0,len(raw),4)])
            expected.extend(values)
        (out/'words.hex').write_text(''.join(f'{w:08x}\n' for xs in words for w in xs))
        (out/'samples.hex').write_text(''.join(f'{v:05x}\n' for v in expected))
        tb='''module tb;
reg clk=0; always #5 clk=~clk;
reg resetn=0,iv=0,ordy=0; wire ir,ov; reg [31:0] data;
wire [9:0] oi,oq;
s3_iq10_unpack dut(clk,resetn,iv,ir,data,ov,ordy,oi,oq);
reg [31:0] words[0:WORDS-1]; reg [19:0] samples[0:SAMPLES-1];
integer sent=0,received=0,cycle=0,epoch=0; reg accepted=0; reg [31:0] rng=32'h53a617d9;
reg stalled=0; reg [19:0] held;
initial begin
 $readmemh("words.hex",words); $readmemh("samples.hex",samples);
 repeat(3) @(negedge clk);resetn=1;
 while(received<SAMPLES) begin
  @(negedge clk);
  // Explicit stopped epoch reset after complete byte/sample drainage.
  if(epoch==0 && received==1048576 && sent==655360) begin
    epoch=1;stalled=0;accepted=0;
    resetn=0;iv=0;ordy=0;@(negedge clk);resetn=1;
  end
  rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
  if(!iv || accepted) begin iv=(sent<(epoch==0 ? 655360 : WORDS) && rng[0:0]);data=words[sent];end
  ordy=rng[3:2]!=0;
  @(posedge clk);
  if(stalled && (!ov || {oq,oi}!==held)) $fatal(1,"unstable under stall");
  stalled=ov&&!ordy;held={oq,oi};
  accepted=iv&&ir;
  if(accepted) sent=sent+1;
  if(ov&&ordy) begin
    if({oq,oi}!==samples[received]) $fatal(1,"sample %0d got %h expected %h",received,{oq,oi},samples[received]);
    received=received+1;
  end
  cycle=cycle+1;
  if(cycle>6000000) $fatal(1,"timeout");
 end
 $display("PASS samples=%0d words=%0d cycles=%0d",received,sent,cycle);$finish;
end
endmodule
'''.replace('WORDS',str(sum(map(len,words)))).replace('SAMPLES',str(len(expected)))
        (out/'tb.sv').write_text(tb)
        subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(ROOT/'rtl/s3_iq10_unpack.sv'),str(out/'tb.sv')],check=True,capture_output=True)
        r=subprocess.run(['vvp','sim'],cwd=out,text=True,capture_output=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('PASS',r.stdout)
        result=dict(test='native IQ10 lossless unpack, independent serialization',samples=len(expected),words=sum(map(len,words)),
                    epochs=2,all_native_values=True,simulator_output=r.stdout.strip(),receiver_adopted=False)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':unittest.main()

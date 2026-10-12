"""Shared physical BSRAM leases must not create a cross-stream dependency."""
from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class PoolTest(unittest.TestCase):
 def test_stalled_RF_does_not_block_FFT_and_offsets_wrap(self):
  for base in (0,0xffffe):
   with self.subTest(base=base):self.run_case(base)
 def run_case(self,base):
  out=ROOT/f'build/s3-pool-{base}';out.mkdir(parents=True,exist_ok=True)
  tb=r'''module tb;
reg clk=0;always #5 clk=~clk;reg rst=0;reg[1:0]iv=0;wire[1:0]ir;
reg[35:0]t0=0,t1=0;wire rv,fv,rl,fl,idle,fault;wire[31:0]rd,fd,ro,fo;reg rr=1,fr=1;
s3_pooled_page_store #(.RESET_RF_SEQUENCE(BASE),.RESET_FFT_SEQUENCE(BASE)) dut(clk,rst,16'd17,iv,ir,t0,t1,1'b0,rv,rr,rd,ro,rl,fv,fr,fd,fo,fl,idle,fault);
integer rf_words=0,fft_words=0,p,w;reg rf_stall=0,fft_stall=0;reg[64:0]rh,fh;reg[31:0]rng=32'h1982abcc;
function[31:0]payload(input integer kind,page,index);payload=(kind<<28)^(page<<16)^index^32'h9b23abcd;endfunction
always @(negedge clk)if(rst)begin rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);fr=rng[3:0]!=0;end
always @(posedge clk)if(rst)begin
 if(fault)$fatal(1,"pool fault");
 if(rf_stall&&(!rv||{rd,ro,rl}!==rh))$fatal(1,"RF held word changed");
 if(fft_stall&&(!fv||{fd,fo,fl}!==fh))$fatal(1,"FFT held word changed");
 rf_stall=rv&&!rr;fft_stall=fv&&!fr;rh={rd,ro,rl};fh={fd,fo,fl};
 if(rv&&rr)begin
  if(rd!==payload(1,rf_words/1024,rf_words%1024)||ro!==((BASE+rf_words/1024)&20'hfffff)*4096||rl!==(rf_words%1024==1023))$fatal(1,"RF identity/order");
  rf_words=rf_words+1;
 end
 if(fv&&fr)begin
  if(fd!==payload(2,fft_words/1024,fft_words%1024)||fo!==((BASE+fft_words/1024)&20'hfffff)*4096||fl!==(fft_words%1024==1023))$fatal(1,"FFT identity/order");
  fft_words=fft_words+1;
 end
end
task send(input integer port,input[35:0]t);begin
 @(negedge clk);if(port==0)t0=t;else t1=t;iv[port]=1;
 @(posedge clk);while(!ir[port])@(posedge clk);
 @(negedge clk);iv[port]=0;
end endtask
task page(input integer port,kind,n);integer i;reg[31:0]off;begin
 off=((BASE+n)&20'hfffff)*4096;
 send(port,{4'h1,kind==1?16'hd711:16'hd712,16'd17});send(port,{4'h2,off});send(port,{4'h3,32'd4096});
 for(i=0;i<1024;i=i+1)send(port,{i==1023?4'h8:4'h0,payload(kind,n,i)});
end endtask
initial begin
 repeat(4)@(negedge clk);rst=1;page(0,1,0);
 wait(rf_words==17);@(negedge clk);rr=0;
 // RF remains stalled mid-page through sixteen complete FFT pages.
 // A single held output creates a deterministic deadlock here.
 for(p=0;p<16;p=p+1)begin page(p%2,2,p);wait(fft_words==(p+1)*1024);end
 if(rf_words!=17||idle)$fatal(1,"stalled RF lost lease");
 @(negedge clk);rr=1;wait(rf_words==1024);
 for(p=1;p<16;p=p+1)begin page(p%2,1,p);wait(rf_words==(p+1)*1024);end
 repeat(8)@(negedge clk);if(!idle||rv||fv||fault)$fatal(1,"leases not retired");
 $display("PASS 32 pages, independent stalled RF/FFT outputs, same offsets, wrap, BSRAM leases");$finish;
end
initial begin #3000000;$fatal(1,"cross-stream deadlock");end
endmodule'''.replace('BASE',str(base))
  (out/'tb.sv').write_text(tb)
  subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(ROOT/'rtl/s3_page_guard.sv'),str(ROOT/'rtl/s3_pooled_page_store.sv'),str(out/'tb.sv')],check=True)
  r=subprocess.run(['vvp',str(out/'sim')],capture_output=True,text=True,timeout=30)
  (out/'simulation.log').write_text(r.stdout+r.stderr);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()

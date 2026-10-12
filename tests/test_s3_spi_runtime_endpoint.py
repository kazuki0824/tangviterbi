"""Actual shared SPI wires: control, native RF, full FFT return and IQ read."""
from pathlib import Path
import random,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class EndpointTest(unittest.TestCase):
 def test_connected_T_endpoint(self):
  out=ROOT/'build/s3-runtime-endpoint-test';out.mkdir(parents=True,exist_ok=True)
  samples=[(i*65537+12345)&0xfffff for i in range(8192)]
  raw=b''.join((a|(b<<20)).to_bytes(5,'little') for a,b in zip(samples[::2],samples[1::2]))
  fft=random.Random(43).randbytes(8192);iq=random.Random(91).randbytes(8192)
  def words(name,data):(out/name).write_text(''.join(f'{int.from_bytes(data[i:i+4],"little"):08x}\n' for i in range(0,len(data),4)))
  words('rf.hex',raw);words('fft.hex',fft);words('iq.hex',iq)
  tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0;always #5.555556 clk=~clk;reg rst=1;
reg s2=0,c2=0,s3=0,c3=0;reg[7:0]d2=0;reg[3:0]d3=0;reg drive=1;wire[3:0]bus3;assign bus3=drive?d3:4'bzzzz;
wire rv,fv,rl,fl,en,fault,br,wr;wire[31:0]rd,fd,ro,fo;wire[15:0]ep;wire[2:0]credit;wire[1:0]pub;
reg rr=1,fr=1,bv=0,wv=0;reg[31:0]off=0,wd=0;
s3_spi_runtime_endpoint dut(clk,rst,1'b1,1'b1,1'b0,s2,c2,d2,s3,c3,bus3,
 rv,rr,rd,ro,rl,fv,fr,fd,fo,fl,bv,br,off,wv,wr,wd,en,fault,ep,credit,pub);
reg[31:0]rfdata[0:5119],fftdata[0:2047],iqdata[0:2047],status[0:7];
integer rn=0,fn=0,i,j,k;reg[7:0]b;reg checking=0;reg[31:0]rng=32'hdd987baf;
always @(negedge clk)if(checking)begin rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);rr=rng[3:0]!=0;fr=rng[7:4]!=0;end
always @(posedge clk)if(checking)begin
 if(fault)$fatal(1,"connected endpoint fault rn=%0d fn=%0d",rn,fn);
 if(rv&&rr)begin if(rn>=5120||rd!==rfdata[rn]||ro!==4096*(rn/1024)||rl!==(rn%1024==1023))$fatal(1,"RF payload/identity");rn=rn+1;end
 if(fv&&fr)begin if(fn>=2048||fd!==fftdata[fn]||fo!==4096*(fn/1024)||fl!==(fn%1024==1023))$fatal(1,"FFT payload/identity");fn=fn+1;end
end
task byte2(input[7:0]x);begin d2=x;#6.25;s2=1;#6.25;s2=0;end endtask
task byte3(input[7:0]x);begin d3=x>>4;#6.25;s3=1;#6.25;s3=0;d3=x;#6.25;s3=1;#6.25;s3=0;end endtask
task read3(output[7:0]x);begin #6.25;s3=1;if(bus3===4'bzzzz)$fatal(1,"missing response");x=bus3<<4;#6.25;s3=0;#6.25;s3=1;x=x|bus3;#6.25;s3=0;end endtask
task header3(input[15:0]cmd,input[15:0]epoch,input[31:0]arg,input[15:0]length);begin
 drive=1;c3=0;byte3(cmd>>8);byte3(cmd);byte3(epoch>>8);byte3(epoch);byte3(arg>>24);byte3(arg>>16);byte3(arg>>8);byte3(arg);byte3(length>>8);byte3(length);
end endtask
task command(input[15:0]cmd,input[15:0]epoch,input[31:0]arg);begin header3(cmd,epoch,arg,0);c3=1;repeat(12)@(negedge clk);end endtask
task query(input[31:0]nonce);integer q;begin
 header3('hd71c,0,nonce,32);drive=0;
 for(q=0;q<32;q=q+1)begin read3(b);status[q/4]=(status[q/4]>>8)|({24'd0,b}<<24);end
 c3=1;drive=1;repeat(8)@(negedge clk);
 if(status[0]!==32'h31534353||status[1]!==32'h01000000+ep||status[4]!==nonce||status[6]!==(status[0]^status[1]^status[2]^status[3]^status[4]^status[5]^32'h96c39a5f)||status[7])$fatal(1,"actual status/epoch ACK");
end endtask
task writepage(input integer kind,page);integer n;reg[31:0]v,a;begin
 a=page*4096;c2=0;byte2('hd7);byte2(kind==1?'h11:'h12);byte2(0);byte2(17);byte2(a>>24);byte2(a>>16);byte2(a>>8);byte2(a);byte2('h10);byte2(0);
 for(n=0;n<1024;n=n+1)begin v=kind==1?rfdata[page*1024+n]:fftdata[page*1024+n];byte2(v);byte2(v>>8);byte2(v>>16);byte2(v>>24);end
 c2=1;#250;
end endtask
initial begin
 $readmemh("rf.hex",rfdata);$readmemh("fft.hex",fftdata);$readmemh("iq.hex",iqdata);
 #1;rst=0;repeat(5)@(negedge clk);c2=1;c3=1;rst=1;repeat(5)@(negedge clk);
 query(1);if(ep||en||fault)$fatal(1,"cold identity");command('hd71d,17,32'h45504f43);query(2);
 if(ep!=17||en||credit||pub||fault)$fatal(1,"fresh epoch");command('hd71e,17,1);query(3);if(!en||!(status[3]&16))$fatal(1,"enable ACK");checking=1;
 fork
  begin
   for(i=0;i<5;i=i+1)begin while(i>=rn/1024+2)@(negedge clk);writepage(1,i);if(i<2)writepage(2,i);end
  end
  begin
   for(j=0;j<2;j=j+1)begin
    @(negedge clk);while(!br)@(negedge clk);off=j*4096;bv=1;@(negedge clk);bv=0;
    for(k=0;k<1024;k=k+1)begin while(!wr)@(negedge clk);wd=iqdata[j*1024+k];wv=1;@(negedge clk);wv=0;end
   end
  end
  begin
   wait(pub==1);#250;header3('hd71b,17,0,4096);drive=0;
   for(integer q=0;q<4096;q=q+1)begin read3(b);if(b!==((iqdata[q/4]>>(8*(q%4)))&255))$fatal(1,"IQ first page");end
   c3=1;drive=1;repeat(10)@(negedge clk);
   wait(pub==3);header3('hd71b,17,4096,4096);drive=0;
   for(integer q=0;q<4096;q=q+1)begin read3(b);if(b!==((iqdata[1024+q/4]>>(8*(q%4)))&255))$fatal(1,"IQ second page");end
   c3=1;drive=1;repeat(10)@(negedge clk);
  end
 join
 wait(rn==5120&&fn==2048);repeat(10)@(negedge clk);query(4);
 if(status[2]!=8192||(status[3]&1)||credit!=(5^(5>>1))||pub!=3)$fatal(1,"retirement/publication/status accounting");
 command('hd71e,17,0);checking=0;query(5);if(en||!(status[3]&4))$fatal(1,"mute/drain ACK");
 command('hd71d,18,32'h45504f43);query(6);if(ep!=18||credit||pub||status[2]||fault)$fatal(1,"epoch reset did not clear all stream cursors");
 $display("PASS connected SPI3 identity/epoch/enable, SPI2 native RF 5 pages and FFT 2 pages, concurrent IQ 2 pages, exact payload, Gray retirement/publication, drain/reset");$finish;
end
initial begin #2000000;$fatal(1,"connected transport deadline/deadlock");end
endmodule'''
  (out/'tb.sv').write_text(tb)
  sources=('s3_async_fifo','s3_spi_rx','s3_page_guard','s3_pooled_page_store','s3_rf_credit','s3_spi_control','s3_spi_iq_pingpong','s3_spi_runtime_endpoint')
  subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'sim'),*[str(ROOT/'rtl'/(s+'.sv')) for s in sources],str(out/'tb.sv')],check=True)
  r=subprocess.run(['vvp','sim'],cwd=out,capture_output=True,text=True,timeout=45)
  (out/'simulation.log').write_text(r.stdout+r.stderr);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()

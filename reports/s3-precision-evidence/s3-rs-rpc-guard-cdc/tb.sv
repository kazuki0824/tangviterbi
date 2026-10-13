`timescale 1ns/1ps
module tb;
reg wclk=0,clk=0;always #(50.0/9.0)wclk=~wclk;always #(500.0/27.0)clk=~clk;
reg rst=0,cv=0,iv=0,last=0,rr=0;reg[7:0]data=0,ckind=2;reg[31:0]cbatch=0;
wire cr,ir,rv;wire[5:0]errors;
s3_rs_rpc_guard_cdc #(.GAP_CYCLES(32)) dut(wclk,clk,rst,cv,cr,ckind,16'd17,cbatch,iv,ir,data,last,rv,rr,errors);
reg[7:0]pages[0:57343],kind[0:13];reg[31:0]batch[0:13];
reg[5:0]mask[0:13];integer length[0:13];
integer t,j,blocked=0,bytes_sent=0,waited;realtime started,maximum=0,elapsed;reg[5:0]held;
task clean_reset;begin
 @(negedge wclk);rst=0;iv=0;cv=0;rr=0;last=0;repeat(6)@(negedge clk);rst=1;repeat(3)@(negedge clk);
end endtask
task start_page;begin
 @(negedge clk);if(!cr)$fatal(1,"config blocked");cv=1;
 @(negedge clk);cv=0;started=$realtime;
end endtask
task send_byte;input[7:0]b;input final_byte;begin
 @(negedge wclk);iv=1;data=b;last=final_byte;
 @(posedge wclk);while(!ir)begin blocked=blocked+1;@(posedge wclk);end
 bytes_sent=bytes_sent+1;@(negedge wclk);iv=0;last=0;
end endtask
initial begin
 $readmemh("pages.hex",pages);kind[0]=2;batch[0]=0;mask[0]=0;length[0]=4096;
kind[1]=4;batch[1]=0;mask[1]=0;length[1]=4096;
kind[2]=2;batch[2]=1;mask[2]=0;length[2]=4096;
kind[3]=4;batch[3]=1;mask[3]=0;length[3]=4096;
kind[4]=2;batch[4]=2;mask[4]=0;length[4]=4096;
kind[5]=4;batch[5]=2;mask[5]=0;length[5]=4096;
kind[6]=2;batch[6]=3;mask[6]=0;length[6]=4096;
kind[7]=4;batch[7]=3;mask[7]=0;length[7]=4096;
kind[8]=2;batch[8]=4;mask[8]=0;length[8]=4096;
kind[9]=4;batch[9]=4;mask[9]=0;length[9]=4096;
kind[10]=2;batch[10]=0;mask[10]=2;length[10]=4096;
kind[11]=2;batch[11]=1;mask[11]=1;length[11]=4096;
kind[12]=2;batch[12]=0;mask[12]=4;length[12]=1000;
kind[13]=2;batch[13]=0;mask[13]=0;length[13]=4096;
 clean_reset();
 for(t=0;t<14;t=t+1)begin
  ckind=kind[t];cbatch=batch[t];start_page();
  for(j=0;j<length[t];j=j+1)begin
   if(j%197==0)repeat(3)@(negedge wclk);
   send_byte(pages[t*4096+j],j==length[t]-1);
  end
  waited=0;while(!rv)begin @(negedge clk);waited=waited+1;if(waited>512)$fatal(1,"no result");end
  elapsed=$realtime-started;if(mask[t]==0&&elapsed>maximum)maximum=elapsed;
  if(mask[t]==0&&errors!=0)$fatal(1,"good page case=%0d errors=%0h",t,errors);
  if(mask[t]!=0&&(errors&mask[t])!=mask[t])$fatal(1,"bad page case=%0d errors=%0h",t,errors);
  held=errors;repeat(7)begin @(negedge clk);if(!rv||errors!==held||cr)$fatal(1,"unstable result");end
  rr=1;@(negedge clk);rr=0;
  if(mask[t]!=0)clean_reset();
 end
 // FIFO may still contain an old byte on a dirty stop. Reset both domains.
 ckind=2;cbatch=0;start_page();send_byte(8'h52,0);clean_reset();
 start_page();send_byte(8'h52,0);repeat(40)@(negedge clk);
 if(!rv||!errors[5])$fatal(1,"missing cross-clock timeout");clean_reset();
 if(rv||!cr)$fatal(1,"reset leaked result");
 if(blocked<10000)$fatal(1,"insufficient backpressure");
 $display("PASS pages=%0d bytes=%0d blocked_writer_cycles=%0d max_good_page_ns=%0.3f",14,bytes_sent,blocked,maximum);$finish;
end
endmodule
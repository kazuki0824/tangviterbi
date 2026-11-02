`timescale 1ns/1ps
module tb;
 reg clk=0,rst=0;always #5 clk=~clk;
 reg[1:0]valid=0;wire[1:0]ready,tc,td,tv,fault;
 reg[15:0]data=0;
 dual_isdb_serial_ts_sinks dut(clk,rst,valid,ready,data,tc,td,tv,fault);
 integer sent0=0,sent1=0,received0=0,received1=0;
 reg[7:0] captured0=0,captured1=0;
 function[7:0] sample(input integer n,input integer lane);
 sample=n%188==0?8'h47:((n*37+lane*19)&255);
 endfunction
 always @(negedge clk)if(rst)begin
  valid[0]=sent0<376 && sent0%13!=7;
  valid[1]=sent1<188 && sent1%11!=6;
  data[7:0]=sample(sent0,0);
  data[15:8]=sample(sent1,1);
 end
 always @(posedge clk)if(rst)begin
  if(valid[0]&&ready[0])sent0<=sent0+1;
  if(valid[1]&&ready[1])sent1<=sent1+1;
  if(fault!=0)$fatal(1,"unexpected TS fault");
 end
 always @(posedge tc[0])if(tv[0])begin
  captured0={captured0[6:0],td[0]};
  received0=received0+1;
  if(received0%8==0&&captured0!==sample(received0/8-1,0))
    $fatal(1,"T serial payload failed byte=%0d got=%h",received0/8-1,captured0);
 end
 always @(posedge tc[1])if(tv[1])begin
  captured1={captured1[6:0],td[1]};
  received1=received1+1;
  if(received1%8==0&&captured1!==sample(received1/8-1,1))
    $fatal(1,"S serial payload failed byte=%0d got=%h",received1/8-1,captured1);
 end
 initial begin
  #1;rst=0;repeat(4)@(negedge clk);rst=1;
  wait(received0==376*8&&received1==188*8);
  if(sent0!=376||sent1!=188)$fatal(1,"TS lost input");
  $display("PASS T two TS packets + S one TS packet; independent 3-wire serial outputs");$finish;
 end
 initial begin #2000000;$fatal(1,"TS deadlock");end
endmodule

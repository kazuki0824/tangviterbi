`timescale 1ns/1ps
module rs_budget_tb;
parameter integer MAX_CYCLES=7118;
reg clk=0; always #5 clk=~clk;
reg resetn=0;
wire ready, valid, fail;
reg [7:0] bytein;
wire [7:0] byteout;
reg [31:0] rng=32'hfdec89;
integer cycles=0, mode, input_count, output_count, start, gap, maxgap=0;
rs204_188_compact dut(.clk(clk),.resetn(resetn),.in_valid(ready),.in_ready(ready),.in_byte(bytein),.out_valid(valid),.out_byte(byteout),.block_fail(fail));
always @(posedge clk) cycles=cycles+1;
initial begin
 for(mode=0; mode<10;mode=mode+1) begin
  @(negedge clk);resetn=0;bytein=0;
  @(negedge clk);resetn=1;start=cycles;input_count=0;output_count=0;
  while(input_count<204) begin
   rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
   if(mode==0)bytein=0;
   else if(mode==1)bytein=input_count<8?8'h01:8'h00;
   else bytein=rng[7:0];
   if(ready)input_count=input_count+1;
   @(negedge clk);
  end
  while(!ready) begin
   if(valid)output_count=output_count+1;
   @(negedge clk);
   if(cycles-start>MAX_CYCLES)$fatal(1,"block service time exceeds stream deadline");
  end
  gap=cycles-start;
  if(gap>maxgap)maxgap=gap;
  if(output_count!=188)$fatal(1,"incomplete output block");
  $display("mode=%0d cycles=%0d outputs=%0d degree=%0d roots=%0d fail=%0d",mode,gap,output_count,dut.bm_l,dut.error_count,fail);
 end
 $display("PASS: RS block deadline, maximum observed=%0d clocks, budget=%0d",maxgap,MAX_CYCLES);$finish;
end
endmodule

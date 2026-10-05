`timescale 1ns/1ps
module rs_budget_tb;
parameter integer MAX_CYCLES=7118;
parameter integer EXPECTED_SAVING=0;
reg clk=0; always #5 clk=~clk;
reg resetn=0, in_valid=0, ref_in_valid=0;
wire ready, valid, fail, ref_ready, ref_valid, ref_fail;
reg [7:0] bytein=0, ref_bytein=0;
wire [7:0] byteout, ref_byteout;
reg [31:0] rng;
reg [7:0] packet [0:203], actual [0:187], expected [0:187];
integer mode, input_count, ref_input_count, output_count, ref_output_count;
integer cycle, start, gap, ref_gap, maxgap=0, max_ref_gap=0, symbol;
rs204_188_compact dut(clk,resetn,in_valid,ready,bytein,valid,byteout,fail);
rs204_188_compact_reference ref_dut(clk,resetn,ref_in_valid,ref_ready,ref_bytein,ref_valid,ref_byteout,ref_fail);
initial begin
 for(mode=0; mode<10; mode=mode+1) begin
  @(negedge clk); resetn=0; in_valid=0; ref_in_valid=0;
  repeat(3) @(negedge clk);
  resetn=1;
  // Build inputs once, independent of latency or ready. Both receive this block.
  rng=32'hfdec89 ^ mode;
  for(symbol=0; symbol<204; symbol=symbol+1) begin
   rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
   if(mode==0)packet[symbol]=0;
   else if(mode==1)packet[symbol]=symbol<8?8'h01:8'h00;
   else packet[symbol]=rng[7:0];
  end
  input_count=0; ref_input_count=0; output_count=0; ref_output_count=0;
  gap=0; ref_gap=0;
  for(cycle=0; cycle<9000 && (gap==0 || ref_gap==0); cycle=cycle+1) begin
   // No input stalls: service includes receive, correction, output and reset.
   in_valid=input_count<204; ref_in_valid=ref_input_count<204;
   bytein=input_count<204?packet[input_count]:0;
   ref_bytein=ref_input_count<204?packet[ref_input_count]:0;
   @(posedge clk);
   if(in_valid && ready)input_count=input_count+1;
   if(ref_in_valid && ref_ready)ref_input_count=ref_input_count+1;
   #1;
   if(valid) begin
    if(output_count>=188)$fatal(1,"extra DUT output");
    actual[output_count]=byteout; output_count=output_count+1;
   end
   if(ref_valid) begin
    if(ref_output_count>=188)$fatal(1,"extra reference output");
    expected[ref_output_count]=ref_byteout; ref_output_count=ref_output_count+1;
   end
   if(input_count==204 && ready && gap==0)gap=cycle+1;
   if(ref_input_count==204 && ref_ready && ref_gap==0)ref_gap=cycle+1;
   @(negedge clk);
  end
  if(gap==0 || gap>MAX_CYCLES)$fatal(1,"block service exceeds stream deadline");
  if(input_count!=204 || ref_input_count!=204 || output_count!=188 || ref_output_count!=188)
   $fatal(1,"incomplete block");
  if(fail !== ref_fail)$fatal(1,"fail mismatch");
  for(symbol=0; symbol<188; symbol=symbol+1)
   if(actual[symbol] !== expected[symbol])$fatal(1,"byte mismatch");
  // Compare identical codewords; changed readiness must not change noisy data.
  if(ref_gap-gap != EXPECTED_SAVING)$fatal(1,"unexpected service saving %0d",ref_gap-gap);
  if(gap>maxgap)maxgap=gap;
  if(ref_gap>max_ref_gap)max_ref_gap=ref_gap;
  $display("mode=%0d cycles=%0d reference=%0d saving=%0d outputs=%0d fail=%0d",mode,gap,ref_gap,ref_gap-gap,output_count,fail);
 end
 $display("PASS: RS block deadline, maximum observed=%0d reference=%0d clocks, budget=%0d",maxgap,max_ref_gap,MAX_CYCLES);
 $finish;
end
endmodule

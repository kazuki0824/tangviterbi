// Comparison boundary; no input queues, depuncture, metric generator or scheduler.
module shared_tc8_k7_boundary #(parameter USE_TC8=1)(
 input wire clk,resetn,slot_valid,output wire slot_ready,
 input wire[1:0]slot_context,output wire[1:0]out_context,
 input wire in_valid,output wire in_ready,input wire[7:0]soft0,soft1,
 input wire[1:0]erasure,output wire out_valid,out_bit,
 input wire in_tc8,input wire[35:0]costs,input wire[3:0]b1_choice,output wire out_b1
);
 generate if(USE_TC8)begin: extended
  shared_tc8_k7_context dut(clk,resetn,slot_valid,slot_ready,slot_context,out_context,
   in_valid,in_ready,soft0,soft1,erasure,out_valid,out_bit,in_tc8,costs,b1_choice,out_b1);
 end else begin: reference_core
  shared_k7_context dut(clk,resetn,slot_valid,slot_ready,slot_context,out_context,
   in_valid,in_ready,soft0,soft1,erasure,out_valid,out_bit);
  assign out_b1=0;
 end endgenerate
endmodule

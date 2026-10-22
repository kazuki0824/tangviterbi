// Partial S TC8PSK chain, signed Q1.15 I/Q, original COST_SHIFT=22.
// Compile with the generated compact s3_tc8psk survivor (22 or 32 ACS).
// This does not include carrier/timing recovery, frame/TMCC, deinterleave,
// RS, TS output or rate-mode switching. Output backpressure is unsupported.
module s_tc8psk_chain(
 input wire clk,resetn,input wire in_valid,output wire in_ready,
 input wire signed[15:0]in_i,in_q,
 output wire out_valid,output wire[1:0]out_bits
);
 wire metric_valid,survivor_ready;
 wire[35:0]costs;wire[3:0]b1_choice;
 s3_tc8psk_metric_folded #(.COST_SHIFT(22)) metric(
 clk,resetn,in_valid,in_ready,in_i,in_q,metric_valid,survivor_ready,costs,b1_choice);
 s3_tc8psk survivor(clk,resetn,metric_valid,survivor_ready,costs,b1_choice,out_valid,out_bits);
endmodule

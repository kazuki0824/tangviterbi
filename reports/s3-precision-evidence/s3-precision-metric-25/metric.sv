// Experimental FPGA SHIFT25 cost quantizer; BER must be checked separately.
// Same exact Q15 dot-product costs as s3_tc8psk_metric, one symbol/3 clocks.
// Native input is unchanged; FPGA branch-cost rounding precision is changed. Compute magnitudes before the
// diagonal multiplies and share two rounding/subtract units over two phases.
// All phases pause under output backpressure; out_valid/data remain stable.
module s3_tc8psk_metric_folded #(parameter COST_SHIFT=25)(
 input wire clk,resetn,
 input wire in_valid,output wire in_ready,
 input wire signed [15:0] in_i,in_q,
 output reg out_valid,input wire out_ready,
 output reg [35:0] costs,output reg [3:0] b1_choice
);
 initial if(COST_SHIFT!=25)$fatal(1,"COST_SHIFT out of range");
 reg [1:0] phase;
 wire advance=!out_valid || out_ready;
 assign in_ready=advance && phase==0;
 wire signed [16:0] isum={in_i[15],in_i}+{in_q[15],in_q};
 wire signed [16:0] idiff={in_q[15],in_q}-{in_i[15],in_i};
 reg [15:0] abs_i,abs_q;
 reg [16:0] abs_sum,abs_diff;
 reg [3:0] input_choice,projection_choice;
 reg input_valid,projection_valid;
 reg [30:0] projection[0:3];
 wire [30:0] max01=projection[0]>projection[1]?projection[0]:projection[1];
 wire [30:0] max23=projection[2]>projection[3]?projection[2]:projection[3];
 reg [30:0] peak;
 wire [30:0] selected_a=phase==0?projection[0]:projection[2];
 wire [30:0] selected_b=phase==0?projection[1]:projection[3];
 function [8:0] quantize;
  input [30:0] delta;
  reg [31:0] rounded;
  begin
   rounded=({1'b0,delta}+(32'd1<<(COST_SHIFT-1)))>>COST_SHIFT;
   quantize={3'd0,rounded[5:0]};
  end
 endfunction
 wire [8:0] cost_a=quantize(peak-selected_a);
 wire [8:0] cost_b=quantize(peak-selected_b);
 always @(posedge clk or negedge resetn) begin
  if(!resetn)begin
   phase<=0;input_valid<=0;projection_valid<=0;
   out_valid<=0;costs<=0;b1_choice<=0;
  end else if(advance)begin
   out_valid<=0;
   if(phase==0)begin
    input_valid<=in_valid;
    abs_i<=in_i[15]?-in_i:in_i;
    abs_q<=in_q[15]?-in_q:in_q;
    abs_sum<=isum[16]?-isum:isum;
    abs_diff<=idiff[16]?-idiff:idiff;
    input_choice<={in_q[15],isum[16],idiff[16],in_i[15]};
    // The previous output was consumed before phase 0 can advance. Fill
    // its low half directly while valid=0; phase 1 publishes both halves.
    costs[17:0]<={cost_b,cost_a};
    phase<=1;
   end else if(phase==1)begin
    projection_valid<=input_valid;
    projection[0]<={abs_i,15'd0};
    projection[1]<=abs_diff*16'd23170;
    projection[2]<=abs_sum*16'd23170;
    projection[3]<={abs_q,15'd0};
    projection_choice<=input_choice;
    out_valid<=projection_valid;
    costs[35:18]<={cost_b,cost_a};
    b1_choice<=projection_choice;
    phase<=2;
   end else begin
    peak<=max01>max23?max01:max23;
    phase<=0;
   end
  end
 end
endmodule

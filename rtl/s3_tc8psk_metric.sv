// BO.1408-1 Fig.15: labels (B1,Y,X), counterclockwise from +I.
// Inputs are carrier/timing-corrected Q1.15 symbols, not raw RF samples.
// Four parallel branches indexed {X,Y}; each chooses its opposite-point B1.
// Dot-product distance with a common per-symbol offset removed. Quantization
// happens HERE in FPGA; there is no SoC sample requantization or decimation.
module s3_tc8psk_metric #(parameter COST_SHIFT=22)(
 input wire clk,resetn,
 input wire in_valid,output wire in_ready,
 input wire signed [15:0] in_i,in_q,
 output wire out_valid,input wire out_ready,
 output reg [35:0] costs,output reg [3:0] b1_choice
);
 initial if(COST_SHIFT<1 || COST_SHIFT>30) $fatal(1,"COST_SHIFT out of range");
 reg [3:0] v;
 wire advance=!v[3] || out_ready;
 assign in_ready=advance;
 assign out_valid=v[3];
 wire signed [16:0] isum={in_i[15],in_i}+{in_q[15],in_q};
 wire signed [16:0] idiff={in_q[15],in_q}-{in_i[15],in_i};
 reg signed [31:0] projection[0:3];
 reg [30:0] magnitude[0:3],aligned_magnitude[0:3];
 reg [3:0] choice2,choice3;
 wire [30:0] max01=magnitude[0]>magnitude[1]?magnitude[0]:magnitude[1];
 wire [30:0] max23=magnitude[2]>magnitude[3]?magnitude[2]:magnitude[3];
 reg [30:0] peak;
 function [8:0] quantize;
  input [30:0] delta;
  reg [31:0] rounded;
  begin
   rounded=({1'b0,delta}+(32'd1<<(COST_SHIFT-1)))>>COST_SHIFT;
   quantize=rounded>511?9'd511:rounded[8:0];
  end
 endfunction
 integer k;
 always @(posedge clk or negedge resetn) begin
  if(!resetn) begin v<=0;costs<=0;b1_choice<=0;end
  else if(advance) begin
   v<={v[2:0],in_valid};
   projection[0]<=$signed({{16{in_i[15]}},in_i})<<<15;
   projection[1]<=idiff*16'sd23170;
   projection[2]<=isum*16'sd23170;
   projection[3]<=$signed({{16{in_q[15]}},in_q})<<<15;
   for(k=0;k<4;k=k+1) begin
    magnitude[k]<=projection[k][31] ? -projection[k] : projection[k];
    choice2[k]<=projection[k][31];
    aligned_magnitude[k]<=magnitude[k];
    costs[9*k+:9]<=quantize(peak-aligned_magnitude[k]);
   end
   peak<=max01>max23?max01:max23;
   choice3<=choice2;b1_choice<=choice3;
  end
 end
endmodule

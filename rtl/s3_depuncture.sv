// ARIB STD-B31 Table 3-8 / ITU-R BO.1408-1 Table 2, X then Y order.
// rate: 0=1/2,1=2/3,2=3/4,3=5/6,4=7/8. Change only at stopped frame boundary.
// Erasures are explicit; a soft value of 127 is NOT an unbiased 8-bit erasure.
module s3_depuncture(
 input wire clk,resetn,frame_start,input wire [2:0] rate,
 input wire in_valid,output wire in_ready,input wire [7:0] in_soft,
 output reg out_valid,input wire out_ready,output reg [7:0] soft_x,soft_y,
 output reg [1:0] erasure,output reg fault
);
 reg [2:0] active_rate,phase;
 reg have_x;reg [7:0] saved_x;
 reg [6:0] mx,my;reg [2:0] period;
 always @* begin
  mx=1;my=1;period=1;
  case(active_rate)
   1:begin mx=7'b0000001;my=7'b0000011;period=2;end
   2:begin mx=7'b0000101;my=7'b0000011;period=3;end
   3:begin mx=7'b0010101;my=7'b0001011;period=5;end
   4:begin mx=7'b1010001;my=7'b0101111;period=7;end
  endcase
 end
 wire x=mx[phase],y=my[phase];
 assign in_ready=!fault && !frame_start && (!out_valid||out_ready);
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin active_rate<=0;phase<=0;have_x<=0;saved_x<=0;out_valid<=0;soft_x<=0;soft_y<=0;erasure<=0;fault<=0;end
  else if(frame_start)begin
   active_rate<=rate;phase<=0;have_x<=0;out_valid<=0;fault<=rate>4;
  end else begin
   if(out_valid&&out_ready)out_valid<=0;
   if(in_valid&&in_ready)begin
    if(x&&y&&!have_x)begin saved_x<=in_soft;have_x<=1;end
    else begin
     soft_x<=x ? (have_x?saved_x:in_soft):8'd0;
     soft_y<=y ? in_soft:8'd0;
     erasure<={!x,!y};have_x<=0;out_valid<=1;
     phase<=phase==period-1?3'd0:phase+1'b1;
    end
   end
  end
 end
endmodule

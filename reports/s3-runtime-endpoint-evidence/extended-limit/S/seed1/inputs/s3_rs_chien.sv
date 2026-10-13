// RS(204,188), roots alpha^0..15, GF 0x11d. Host supplies ascending locator
// coefficients; each reported position is a byte index 0..203. Root records
// must remain unpublished until done_fail is known. No received byte changes.
module s3_rs_chien(
 input wire clk,resetn,
 input wire command_valid,output wire command_ready,
 input wire [71:0] locator,input wire [3:0] degree,
 output reg root_valid,input wire root_ready,output reg [7:0] root_position,
 output wire done_valid,input wire done_ready,output reg done_fail,
 output reg [3:0] root_count
);
 reg busy,finished;reg [7:0] position,lambda0;
 reg [3:0] degree_q;
 reg [7:0] term[0:7];
 assign command_ready=!busy && !finished && !root_valid;
 assign done_valid=finished && !root_valid;
 function [7:0] multiply;
  input [7:0] a,b;integer k;reg [7:0] x,y;
  begin x=a;y=0;for(k=0;k<8;k=k+1)begin
   if(b[k])y=y^x;x={x[6:0],1'b0}^(x[7]?8'h1d:8'd0);
  end multiply=y;end
 endfunction
 function [7:0] alpha;
  input integer exponent;integer k;reg [7:0] x;
  begin x=1;for(k=0;k<exponent;k=k+1)x={x[6:0],1'b0}^(x[7]?8'h1d:8'd0);alpha=x;end
 endfunction
 wire [7:0] evaluation=lambda0^term[0]^term[1]^term[2]^term[3]^term[4]^term[5]^term[6]^term[7];
 wire advance=busy && (!root_valid || root_ready);
 genvar n;
 generate for(n=0;n<8;n=n+1)begin:terms
  always @(posedge clk)begin
   if(resetn && command_valid && command_ready)
    term[n]<=n<degree?multiply(locator[(n+1)*8+:8],alpha((52*(n+1))%255)):0;
   else if(resetn && advance)term[n]<=multiply(term[n],alpha(n+1));
  end
 end endgenerate
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin busy<=0;finished<=0;position<=0;lambda0<=0;degree_q<=0;
   root_valid<=0;root_position<=0;root_count<=0;done_fail<=0;end
  else begin
   if(root_valid && root_ready)root_valid<=0;
   if(done_valid && done_ready)finished<=0;
   if(command_valid && command_ready)begin
    position<=0;lambda0<=locator[7:0];degree_q<=degree;root_count<=0;
    done_fail<=degree>8 || locator[7:0]!=1;
    busy<=degree!=0 && degree<=8 && locator[7:0]==1;
    finished<=degree==0 || degree>8 || locator[7:0]!=1;
   end else if(advance)begin
    if(evaluation==0)begin
     if(root_count<8)begin root_position<=position;root_valid<=1;root_count<=root_count+1'b1;end
     else done_fail<=1;
    end
    if(position==203)begin
     busy<=0;finished<=1;
     if(root_count+(evaluation==0?1:0)!=degree_q)done_fail<=1;
    end else position<=position+1'b1;
   end
  end
 end
endmodule

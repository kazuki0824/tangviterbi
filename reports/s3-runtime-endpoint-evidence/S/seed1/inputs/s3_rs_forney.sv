// RS(204,188), roots alpha^0..15, GF(256)/0x11d, shortening by 51.
// CPU provides BM/Omega; Chien provides sorted byte positions. One multiplier
// is shared by Horner evaluation and inversion. No received bytes are stored.
// This module is a partition experiment; it is not a complete receiver.
module s3_rs_forney(
 input wire clk,resetn,
 input wire cmd_valid,output wire cmd_ready,
 input wire [71:0] cmd_lambda,input wire [127:0] cmd_omega,
 input wire [3:0] cmd_degree,cmd_count,input wire [63:0] cmd_positions,
 output wire out_valid,input wire out_ready,
 output reg out_failed,output reg [63:0] out_magnitudes
);
 localparam IDLE=0,SEEK=1,LOCATOR=2,OMEGA=3,SQUARE=4,DERIV=5,
  DENOM=6,INV_SQUARE=7,INV_MULTIPLY=8,MAGNITUDE=9,PUBLISH=10;
 reg [3:0] state,count;
 reg [2:0] error_index,inverse_bit;
 reg [4:0] terms;
 reg [71:0] lambda,polynomial;
 reg [127:0] omega,omega_shift;
 reg [31:0] odd,odd_shift;
 reg [63:0] positions;
 reg [7:0] root,root_position,previous,acc,x2,numerator,denominator,inverse;
 reg [7:0] ma,mb;
 wire [7:0] product;
 function [7:0] multiply;
  input [7:0] a,b;
  reg [7:0] x,y,z;integer i;
  begin
   x=a;y=b;z=0;
   for(i=0;i<8;i=i+1)begin
    if(y[0])z=z^x;
    x=(x<<1)^(x[7]?8'h1d:8'h00);y=y>>1;
   end
   multiply=z;
  end
 endfunction
 assign product=multiply(ma,mb);
 assign cmd_ready=state==IDLE;
 assign out_valid=state==PUBLISH;
 always @* begin
  ma=acc;mb=root;
  case(state)
   SQUARE:begin ma=root;mb=root;end
   DERIV:mb=x2;
   DENOM:mb=root;
   INV_SQUARE:begin ma=inverse;mb=inverse;end
   INV_MULTIPLY:begin ma=inverse;mb=denominator;end
   MAGNITUDE:begin ma=numerator;mb=inverse;end
   default:begin end
  endcase
 end
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   state<=IDLE;count<=0;error_index<=0;inverse_bit<=0;terms<=0;
   lambda<=0;polynomial<=0;omega<=0;omega_shift<=0;odd<=0;odd_shift<=0;
   positions<=0;root<=0;root_position<=0;previous<=0;acc<=0;x2<=0;
   numerator<=0;denominator<=0;inverse<=0;out_failed<=0;out_magnitudes<=0;
  end else begin
   case(state)
    IDLE:if(cmd_valid)begin
     lambda<=cmd_lambda;omega<=cmd_omega;positions<=cmd_positions;
     // Lowest byte first: lambda7,lambda5,lambda3,lambda1.
     odd<={cmd_lambda[15:8],cmd_lambda[31:24],cmd_lambda[47:40],cmd_lambda[63:56]};
     count<=cmd_count;error_index<=0;root<=8'h14;root_position<=0;previous<=0;
     out_magnitudes<=0;
     out_failed<=cmd_degree>8 || cmd_count!=cmd_degree || cmd_lambda[7:0]!=1;
     if(cmd_degree>8 || cmd_count!=cmd_degree || cmd_lambda[7:0]!=1 || cmd_count==0)
      state<=PUBLISH;
     else state<=SEEK;
    end
    SEEK:begin
     if(positions[7:0]>=204 || (error_index!=0 && positions[7:0]<=previous))begin
      out_failed<=1;state<=PUBLISH;
     end else if(root_position==positions[7:0])begin
      polynomial<=lambda;acc<=0;terms<=9;state<=LOCATOR;
     end else begin
      root<=(root<<1)^(root[7]?8'h1d:8'h00);root_position<=root_position+1'b1;
     end
    end
    LOCATOR:begin
     acc<=product^polynomial[71:64];polynomial<=polynomial<<8;terms<=terms-1'b1;
     if(terms==1)begin
      if((product^polynomial[71:64])!=0)begin out_failed<=1;state<=PUBLISH;end
      else begin acc<=0;omega_shift<=omega;terms<=16;state<=OMEGA;end
     end
    end
    OMEGA:begin
     acc<=product^omega_shift[127:120];omega_shift<=omega_shift<<8;terms<=terms-1'b1;
     if(terms==1)begin numerator<=product^omega_shift[127:120];state<=SQUARE;end
    end
    SQUARE:begin x2<=product;acc<=0;odd_shift<=odd;terms<=4;state<=DERIV;end
    DERIV:begin
     acc<=product^odd_shift[7:0];odd_shift<=odd_shift>>8;terms<=terms-1'b1;
     if(terms==1)state<=DENOM;
    end
    DENOM:begin
     denominator<=product;
     if(product==0)begin out_failed<=1;state<=PUBLISH;end
     else begin inverse<=1;inverse_bit<=7;state<=INV_SQUARE;end
    end
    // Binary exponent 254: seven square/multiply pairs and one final square.
    INV_SQUARE:begin
     inverse<=product;
     if(inverse_bit==0)state<=MAGNITUDE;else state<=INV_MULTIPLY;
    end
    INV_MULTIPLY:begin inverse<=product;inverse_bit<=inverse_bit-1'b1;state<=INV_SQUARE;end
    MAGNITUDE:begin
     out_magnitudes[8*error_index+:8]<=product;previous<=positions[7:0];
     if(error_index+1'b1==count)state<=PUBLISH;
     else begin positions<=positions>>8;error_index<=error_index+1'b1;state<=SEEK;end
    end
    PUBLISH:if(out_ready)state<=IDLE;
    default:state<=IDLE;
   endcase
  end
 end
endmodule

// Exact GF(256) RS(204,188) syndrome accumulation with registered ROM
// addresses. Two 2048x8 ROMs; ten core clocks per input byte without stalls.
// No change to byte precision or field polynomial. A completed output remains
// immutable until out_ready. Reset discards partial blocks; the first byte
// overwrites every syndrome, so uncleared RAM/register values cannot escape.
module s3_rs_syndrome(
 input wire clk,resetn,input wire in_valid,output wire in_ready,input wire [7:0] in_byte,
 output reg out_valid,input wire out_ready,output wire [127:0] syndromes
);
 (* ram_style="block" *) reg [7:0] rom_even[0:2047],rom_odd[0:2047];
 reg [7:0] even[0:7],odd[0:7];
 reg [7:0] q_even,q_odd,byte_q,accepted;
 reg [10:0] address_even,address_odd;
 reg [2:0] read_phase,address_phase,value_phase;
 reg busy,reading,first_byte,last_byte,address_valid,value_valid;
 assign in_ready=!busy&&!out_valid&&!last_byte;
 wire take=in_valid&&in_ready;
 wire request=take||(busy&&reading);
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
 integer a,n;
 initial for(n=0;n<8;n=n+1)for(a=0;a<256;a=a+1)begin
  rom_even[n*256+a]=multiply(a,alpha(2*n));
  rom_odd[n*256+a]=multiply(a,alpha(2*n+1));
 end
 always @(posedge clk)begin
  if(request)begin
   address_even<={read_phase,even[read_phase]};
   address_odd<={read_phase,odd[read_phase]};
  end
  if(address_valid)begin q_even<=rom_even[address_even];q_odd<=rom_odd[address_odd];end
 end
 genvar j;generate for(j=0;j<8;j=j+1)begin:values
  assign syndromes[(2*j)*8+:8]=even[j];
  assign syndromes[(2*j+1)*8+:8]=odd[j];
  always @(posedge clk)if(resetn&&value_valid&&value_phase==j)begin
   even[j]<=(first_byte?8'd0:q_even)^byte_q;
   odd[j]<=(first_byte?8'd0:q_odd)^byte_q;
  end
 end endgenerate
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   busy<=0;reading<=0;first_byte<=0;last_byte<=0;accepted<=0;byte_q<=0;
   address_valid<=0;value_valid<=0;read_phase<=0;address_phase<=0;value_phase<=0;
   out_valid<=0;
  end else begin
   address_valid<=request;value_valid<=address_valid;
   if(request)address_phase<=read_phase;
   if(address_valid)value_phase<=address_phase;
   if(out_valid&&out_ready)begin out_valid<=0;accepted<=0;last_byte<=0;end
   if(take)begin
    busy<=1;reading<=1;read_phase<=1;
    byte_q<=in_byte;first_byte<=accepted==0;last_byte<=accepted==203;
    accepted<=accepted+1'b1;
   end else if(busy&&reading)begin
    if(read_phase==7)begin reading<=0;read_phase<=0;end
    else read_phase<=read_phase+1'b1;
   end
   if(value_valid&&value_phase==7)begin
    busy<=0;
    if(last_byte)out_valid<=1;
   end
  end
 end
endmodule

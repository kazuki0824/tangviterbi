// Two GF lookup ports fold 16 syndromes over 8 clocks/byte. ROMs are each
// 2048x8 (one BSRAM per parity of root number). Block output is ascending S0..15.
// Byte count and valid bound block ownership; no extra sample quantization.
module s3_rs_syndrome(
 input wire clk,resetn,input wire in_valid,output wire in_ready,input wire[7:0] in_byte,
 output reg out_valid,input wire out_ready,output wire[127:0] syndromes
);
 (* ram_style="block" *) reg[7:0] rom_even[0:2047],rom_odd[0:2047];
 reg[7:0] even[0:7],odd[0:7];
 reg[7:0] q_even,q_odd,byte_q;
 reg[7:0] accepted;
 reg busy,reading,first_byte;
 reg[2:0] read_phase,write_phase;
 // The next byte may start on the edge which writes syndrome pair 7 of
 // the previous byte; pair 0 has been stable for seven clocks by then.
 assign in_ready=!out_valid && accepted<204 && (!busy || (!reading && write_phase==7));
 wire take=in_valid && in_ready;
 wire request=take || (busy && reading);
 wire[2:0] address_phase=take?3'd0:read_phase;
 function [7:0] multiply;
  input[7:0] a,b;integer k;reg[7:0] x,y;
  begin x=a;y=0;for(k=0;k<8;k=k+1)begin
   if(b[k])y=y^x;x={x[6:0],1'b0}^(x[7]?8'h1d:8'd0);
  end multiply=y;end
 endfunction
 function [7:0] alpha;
  input integer exponent;integer k;reg[7:0] x;
  begin x=1;for(k=0;k<exponent;k=k+1)x={x[6:0],1'b0}^(x[7]?8'h1d:8'd0);alpha=x;end
 endfunction
 integer a,n;
 initial for(n=0;n<8;n=n+1)for(a=0;a<256;a=a+1)begin
  rom_even[n*256+a]=multiply(a,alpha(2*n));
  rom_odd[n*256+a]=multiply(a,alpha(2*n+1));
 end
 always @(posedge clk)if(request)begin
  q_even<=rom_even[{address_phase,even[address_phase]}];
  q_odd<=rom_odd[{address_phase,odd[address_phase]}];
 end
 genvar j;
 generate for(j=0;j<8;j=j+1)begin:values
  assign syndromes[(2*j)*8+:8]=even[j];
  assign syndromes[(2*j+1)*8+:8]=odd[j];
  always @(posedge clk)if(resetn && busy && write_phase==j)begin
   even[j]<=(first_byte?8'd0:q_even)^byte_q;
   odd[j]<=(first_byte?8'd0:q_odd)^byte_q;
  end
 end endgenerate
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin busy<=0;reading<=0;accepted<=0;byte_q<=0;first_byte<=0;
   read_phase<=0;write_phase<=0;out_valid<=0;end
  else begin
   if(out_valid && out_ready)begin out_valid<=0;accepted<=0;end
   if(busy)begin
    if(reading)begin
     write_phase<=read_phase;
     if(read_phase==7)reading<=0;else read_phase<=read_phase+1'b1;
    end else begin
     busy<=0;
     if(accepted==204)out_valid<=1;
    end
   end
   if(take)begin
    busy<=1;reading<=1;read_phase<=1;write_phase<=0;
    byte_q<=in_byte;first_byte<=accepted==0;accepted<=accepted+1'b1;
   end
  end
 end
endmodule

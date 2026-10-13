// Experimental four-port syndrome, no quantization or changed code.
module s3_rs_syndrome(input wire clk,resetn,input wire in_valid,output wire in_ready,
 input wire[7:0] in_byte,output reg out_valid,input wire out_ready,output wire[127:0] syndromes);
 reg[7:0] accepted,byte_q;
 reg busy,reading,first_byte,last_byte;
 reg[1:0] read_phase,write_phase;
 assign in_ready=!out_valid && !last_byte && (!busy || (!reading && write_phase==3));
 wire take=in_valid && in_ready;
 wire request=take || (busy && reading);
 wire[1:0] address_phase=take?2'd0:read_phase;
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

 (* ram_style="block" *) reg[7:0] rom0[0:1023];
 reg[7:0] values0[0:3];reg[7:0] q0;
 initial for(n=0;n<4;n=n+1)for(a=0;a<256;a=a+1)rom0[n*256+a]=multiply(a,alpha(4*n+0));
 always @(posedge clk)if(request)q0<=rom0[{address_phase,values0[address_phase]}];
 assign syndromes[0+:8]=values0[0];
 always @(posedge clk)if(resetn && busy && write_phase==2'd0)
  values0[0]<=(first_byte?8'd0:q0)^byte_q;
 assign syndromes[32+:8]=values0[1];
 always @(posedge clk)if(resetn && busy && write_phase==2'd1)
  values0[1]<=(first_byte?8'd0:q0)^byte_q;
 assign syndromes[64+:8]=values0[2];
 always @(posedge clk)if(resetn && busy && write_phase==2'd2)
  values0[2]<=(first_byte?8'd0:q0)^byte_q;
 assign syndromes[96+:8]=values0[3];
 always @(posedge clk)if(resetn && busy && write_phase==2'd3)
  values0[3]<=(first_byte?8'd0:q0)^byte_q;
 (* ram_style="block" *) reg[7:0] rom1[0:1023];
 reg[7:0] values1[0:3];reg[7:0] q1;
 initial for(n=0;n<4;n=n+1)for(a=0;a<256;a=a+1)rom1[n*256+a]=multiply(a,alpha(4*n+1));
 always @(posedge clk)if(request)q1<=rom1[{address_phase,values1[address_phase]}];
 assign syndromes[8+:8]=values1[0];
 always @(posedge clk)if(resetn && busy && write_phase==2'd0)
  values1[0]<=(first_byte?8'd0:q1)^byte_q;
 assign syndromes[40+:8]=values1[1];
 always @(posedge clk)if(resetn && busy && write_phase==2'd1)
  values1[1]<=(first_byte?8'd0:q1)^byte_q;
 assign syndromes[72+:8]=values1[2];
 always @(posedge clk)if(resetn && busy && write_phase==2'd2)
  values1[2]<=(first_byte?8'd0:q1)^byte_q;
 assign syndromes[104+:8]=values1[3];
 always @(posedge clk)if(resetn && busy && write_phase==2'd3)
  values1[3]<=(first_byte?8'd0:q1)^byte_q;
 (* ram_style="block" *) reg[7:0] rom2[0:1023];
 reg[7:0] values2[0:3];reg[7:0] q2;
 initial for(n=0;n<4;n=n+1)for(a=0;a<256;a=a+1)rom2[n*256+a]=multiply(a,alpha(4*n+2));
 always @(posedge clk)if(request)q2<=rom2[{address_phase,values2[address_phase]}];
 assign syndromes[16+:8]=values2[0];
 always @(posedge clk)if(resetn && busy && write_phase==2'd0)
  values2[0]<=(first_byte?8'd0:q2)^byte_q;
 assign syndromes[48+:8]=values2[1];
 always @(posedge clk)if(resetn && busy && write_phase==2'd1)
  values2[1]<=(first_byte?8'd0:q2)^byte_q;
 assign syndromes[80+:8]=values2[2];
 always @(posedge clk)if(resetn && busy && write_phase==2'd2)
  values2[2]<=(first_byte?8'd0:q2)^byte_q;
 assign syndromes[112+:8]=values2[3];
 always @(posedge clk)if(resetn && busy && write_phase==2'd3)
  values2[3]<=(first_byte?8'd0:q2)^byte_q;
 (* ram_style="block" *) reg[7:0] rom3[0:1023];
 reg[7:0] values3[0:3];reg[7:0] q3;
 initial for(n=0;n<4;n=n+1)for(a=0;a<256;a=a+1)rom3[n*256+a]=multiply(a,alpha(4*n+3));
 always @(posedge clk)if(request)q3<=rom3[{address_phase,values3[address_phase]}];
 assign syndromes[24+:8]=values3[0];
 always @(posedge clk)if(resetn && busy && write_phase==2'd0)
  values3[0]<=(first_byte?8'd0:q3)^byte_q;
 assign syndromes[56+:8]=values3[1];
 always @(posedge clk)if(resetn && busy && write_phase==2'd1)
  values3[1]<=(first_byte?8'd0:q3)^byte_q;
 assign syndromes[88+:8]=values3[2];
 always @(posedge clk)if(resetn && busy && write_phase==2'd2)
  values3[2]<=(first_byte?8'd0:q3)^byte_q;
 assign syndromes[120+:8]=values3[3];
 always @(posedge clk)if(resetn && busy && write_phase==2'd3)
  values3[3]<=(first_byte?8'd0:q3)^byte_q;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin busy<=0;reading<=0;accepted<=0;byte_q<=0;first_byte<=0;last_byte<=0;
   read_phase<=0;write_phase<=0;out_valid<=0;end
  else begin
   if(out_valid && out_ready)begin out_valid<=0;accepted<=0;last_byte<=0;end
   if(busy)begin
    if(reading)begin
     write_phase<=read_phase;
     if(read_phase==3)reading<=0;else read_phase<=read_phase+1'b1;
    end else begin busy<=0;if(last_byte)out_valid<=1;end
   end
   if(take)begin
    busy<=1;reading<=1;read_phase<=1;write_phase<=0;
    last_byte<=accepted==203;byte_q<=in_byte;first_byte<=accepted==0;accepted<=accepted+1'b1;
   end
  end
 end
endmodule

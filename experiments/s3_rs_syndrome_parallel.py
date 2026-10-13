"""Four GF lookup ports, four clocks/byte, exact same 16 syndrome contract."""
def source():
 lines=['''// Experimental four-port syndrome, no quantization or changed code.
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
''']
 for g in range(4):
  lines.append(f''' (* ram_style="block" *) reg[7:0] rom{g}[0:1023];
 reg[7:0] values{g}[0:3];reg[7:0] q{g};
 initial for(n=0;n<4;n=n+1)for(a=0;a<256;a=a+1)rom{g}[n*256+a]=multiply(a,alpha(4*n+{g}));
 always @(posedge clk)if(request)q{g}<=rom{g}[{{address_phase,values{g}[address_phase]}}];''')
  for j in range(4):
   lines.append(f''' assign syndromes[{(4*j+g)*8}+:8]=values{g}[{j}];
 always @(posedge clk)if(resetn && busy && write_phase==2'd{j})
  values{g}[{j}]<=(first_byte?8'd0:q{g})^byte_q;''')
 lines.append(''' always @(posedge clk or negedge resetn)begin
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
endmodule''')
 return '\n'.join(lines)+'\n'
if __name__=='__main__':print(source())

// 256 retained S words including the prefetched head. Same clock, lossless.
// Binary mode uses low 8 bits; TC8 uses the full signed Q15 IQ word.
module s_input_fifo(input wire clk,resetn,input wire in_valid,output wire in_ready,
 input wire[31:0]in_data,output reg out_valid,input wire out_ready,
 output reg[31:0]out_data);
 (* ram_style="block" *) reg[31:0]words[0:255];
 reg[7:0]wr_ptr,rd_ptr;reg[8:0]count;
 wire put=in_valid&&in_ready;
 wire take=count!=0 && (!out_valid||out_ready);
 assign in_ready=resetn && (count+out_valid<256);
 always @(posedge clk)begin
  if(put)words[wr_ptr]<=in_data;
  if(take)out_data<=words[rd_ptr];
 end
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin wr_ptr<=0;rd_ptr<=0;count<=0;out_valid<=0;end
  else begin
   if(put)wr_ptr<=wr_ptr+1'b1;
   if(take)begin rd_ptr<=rd_ptr+1'b1;out_valid<=1;end
   else if(out_ready)out_valid<=0;
   case({put,take})
    2'b10:count<=count+1'b1;
    2'b01:count<=count-1'b1;
    default:;
   endcase
  end
 end
endmodule

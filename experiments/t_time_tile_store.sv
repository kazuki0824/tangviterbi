// Experimental 16x16 tile of unchanged six-byte soft samples.
// A row or column is transferred per block. Independent read/write engines may
// overlap only for disjoint sample addresses. Caller owns tile lifetime.
module t_time_tile_store(
 input wire clk,resetn,
 input wire put_valid,output wire put_ready,input wire put_column,
 input wire[3:0] put_index,input wire[767:0] put_data,
 input wire get_valid,output wire get_ready,input wire get_column,
 input wire[3:0] get_index,output wire result_valid,input wire result_ready,
 output wire[767:0] result_data,output reg collision
);
 reg[47:0] samples[0:255];
 reg writing,reading,pending,out_valid;
 reg wc,rc;reg[3:0]wi,ri,wp,rp;reg[4:0]received;
 reg[767:0] wbuf,rbuf;reg[47:0]q;
 wire[7:0]wa=wc?{wp,wi}:{wi,wp};
 wire[7:0]ra=rc?{rp,ri}:{ri,rp};
 assign put_ready=resetn&&!writing;
 assign get_ready=resetn&&!reading&&!pending&&!out_valid;
 assign result_valid=resetn&&out_valid;
 assign result_data=rbuf;
 always @(posedge clk)begin
  if(writing)samples[wa]<=wbuf[47:0];
  if(reading)q<=samples[ra];
 end
 always @(posedge clk)begin
  if(!resetn)begin
   writing<=0;reading<=0;pending<=0;out_valid<=0;collision<=0;
   wc<=0;rc<=0;wi<=0;ri<=0;wp<=0;rp<=0;received<=0;
  end else begin
   if(writing&&reading&&wa==ra)collision<=1;
   if(put_valid&&put_ready)begin writing<=1;wc<=put_column;wi<=put_index;wp<=0;wbuf<=put_data;end
   if(writing)begin
    wbuf<=wbuf>>48;wp<=wp+1'b1;if(wp==15)writing<=0;
   end
   if(result_valid&&result_ready)out_valid<=0;
   if(get_valid&&get_ready)begin reading<=1;rc<=get_column;ri<=get_index;rp<=0;received<=0;end
   pending<=reading;
   if(reading)begin rp<=rp+1'b1;if(rp==15)reading<=0;end
   if(pending)begin
    rbuf<={q,rbuf[767:48]};received<=received+1'b1;
    if(received==15)out_valid<=1;
   end
  end
 end
endmodule

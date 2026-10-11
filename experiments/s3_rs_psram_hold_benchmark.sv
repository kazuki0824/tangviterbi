// Synthetic driver around a real 512-slot codeword store and native PSRAM IO.
// Co-placement prerequisite only: input is not the connected RF/FEC stream.
module s3_rs_psram_hold_benchmark(
 input wire clk,clk_ck,resetn,input wire [7:0] stimulus,
 output wire activity,
 output wire [1:0] O_psram_ck,O_psram_ck_n,O_psram_cs_n,O_psram_reset_n,
 inout wire [15:0] IO_psram_dq,inout wire [1:0] IO_psram_rwds
);
 wire iv,ir,av,at,rr,rready,rvalid,rlast,qf,sf;
 wire [20:0] wa,ra,ca;wire [31:0] wd,rd,bwd,brd;
 wire cv,cr,cw,wv,wr,rv,done,init,bf,pr,pc,pk,pd,pw,re,pf;
 wire [15:0] tf,ts,x0,x1;wire [1:0] xv;
 wire commit,request_ready,out_valid,out_last,retire;
 wire [7:0] out_data;wire [9:0] held;
 reg [3:0] pace;
 reg [31:0] checksum;
 reg stop;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin pace<=0;checksum<=0;stop<=0;end
  else begin
   pace<=pace==9?0:pace+1'b1;
   if(out_valid)checksum<={checksum[30:0],checksum[31]}^out_data;
   if(qf||sf||bf||pf)stop<=1;
  end
 end
 s3_rs_psram_store store(clk,resetn,stop,init&&pace==0,ir,stimulus,commit,
  held>=204,request_ready,out_valid,1'b1,out_data,out_last,retire,
  iv,rready,wa,wd,av,rr,rvalid,ra,wv,wr,rd,rlast,held,sf);
 s3_psram_queue queue(clk,resetn,stop,iv,rready,1'b0,wa,wd,av,at,
  rr,rvalid,ra,wv,wr,rd,rlast,cv,cr,cw,ca,
  ir_unused,wr_unused,bwd,rv,brd,done,bf,qf);
 wire ir_unused,wr_unused;
 s3_psram_burst controller(clk,resetn,stop,cv,cw,ca,cr,ir_unused,bwd,wr_unused,
  rv,brd,done,init,bf,pr,pc,pk,pd,pw,tf,ts,re,xv,x0,x1,pf);
 s3_psram_phy phy(clk,clk_ck,resetn,pr,pc,pk,pd,pw,tf,ts,re,xv,x0,x1,pf,
  O_psram_ck,O_psram_ck_n,O_psram_cs_n,O_psram_reset_n,IO_psram_dq,IO_psram_rwds);
 assign activity=^{checksum,held,commit,request_ready,out_last,retire,at,ir,stop};
endmodule

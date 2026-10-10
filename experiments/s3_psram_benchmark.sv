// Standalone physical-pin memory BIST, not a receiver. Sequentially writes
// and reads all 8 MiB with an address-dependent pattern. LEDs latch status.
module s3_psram_benchmark(
 input wire clk27,resetn,output wire [5:0] led,
 output wire [1:0] O_psram_ck,O_psram_ck_n,O_psram_cs_n,O_psram_reset_n,
 inout wire [15:0] IO_psram_dq,inout wire [1:0] IO_psram_rwds
);
 wire clk,clk_ck,rst;
 s3_psram_clock clocking(clk27,resetn,clk,clk_ck,rst);
 wire cv,cr,cw,wv,wr,rv,done,init,fault,pr,pc,pk,pd,pw,re,pf;
 wire [20:0] ca;wire [31:0] wd,rd;wire [15:0] tf,ts,x0,x1;wire [1:0] xv;
 wire iv,ir,av,at,rr,rready,rvalid,rlast,qf;wire [31:0] rdata;
 reg [20:0] write_address,read_address;
 reg [21:0] written;
 reg reading,read_pending,finished,compare_fault;
 reg [5:0] read_index;
 wire [20:0] expected_address={read_address[20:6],read_index};
 wire [31:0] pattern={write_address,11'b10101011001} ^ (32'h15c339a7+{11'd0,write_address});
 wire [31:0] expected={expected_address,11'b10101011001} ^ (32'h15c339a7+{11'd0,expected_address});
 assign iv=init&&!reading&&!finished&&!compare_fault;
 assign rr=reading&&!read_pending&&!finished&&!compare_fault;
 always @(posedge clk or negedge rst)begin
  if(!rst)begin write_address<=0;read_address<=0;written<=0;reading<=0;read_pending<=0;finished<=0;compare_fault<=0;read_index<=0;end
  else begin
   if(iv&&ir)begin write_address<=write_address+1'b1;if(write_address==21'h1fffff)reading<=1;end
   if(av)written<=written+1'b1;
   if(rr&&rready&&written==22'h200000)read_pending<=1;
   if(rvalid)begin
    if(rdata!=expected)compare_fault<=1;
    read_index<=read_index+1'b1;
    if(rlast)begin
     read_pending<=0;read_address<=read_address+21'd64;
     if(read_address==21'h1fffc0)finished<=1;
    end
   end
  end
 end
 s3_psram_queue queue(clk,rst,compare_fault,iv,ir,write_address[6],write_address,pattern,av,at,
  rr&&written==22'h200000,rready,read_address,rvalid,1'b1,rdata,rlast,
  cv,cr,cw,ca,wv,wr,wd,rv,rd,done,fault,qf);
 s3_psram_burst controller(clk,rst,qf,cv,cw,ca,cr,wv,wd,wr,rv,rd,done,init,fault,
  pr,pc,pk,pd,pw,tf,ts,re,xv,x0,x1,pf);
 s3_psram_phy phy(clk,clk_ck,rst,pr,pc,pk,pd,pw,tf,ts,re,xv,x0,x1,pf,
  O_psram_ck,O_psram_ck_n,O_psram_cs_n,O_psram_reset_n,IO_psram_dq,IO_psram_rwds);
 assign led=~{compare_fault,qf,fault,finished,reading,init};
endmodule

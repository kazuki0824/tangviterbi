// Gowin 1:1 DDR PHY candidate. clk_ck must be clk +90 degrees (not an
// unrelated clock). This source instantiates real ODDR/IDDR primitives; the
// test model implements their UG289 edge ordering. Neither model nor core P&R
// establishes the external DQ/RWDS eye. Phase/IO constraints and board BIST
// are mandatory before this may be called a working hardware PHY.
module s3_psram_phy(
 input wire clk,clk_ck,resetn,
 input wire ram_reset_n,ram_cs_n,ram_ck_enable,dq_drive,rwds_drive,
 input wire [15:0] tx_first,tx_second,input wire rx_enable,
 output reg [1:0] rx_valid,output reg [15:0] rx_word0,rx_word1,
 output reg fault,
 output wire [1:0] O_psram_ck,O_psram_ck_n,O_psram_cs_n,O_psram_reset_n,
 inout wire [15:0] IO_psram_dq,inout wire [1:0] IO_psram_rwds
);
 wire [15:0] q0,q1,dq_out,dq_disable;
 wire [1:0] strobe0,strobe1,rwds_out,rwds_disable;
 reg clock_launch;
 // Capture between core launches: the next clk_ck rising edge is 3/4 of a
 // core period away. Capturing on clk's rising edge would leave only 1/4.
 always @(negedge clk or negedge resetn)
  if(!resetn)clock_launch<=0;else clock_launch<=ram_ck_enable;
 assign O_psram_reset_n={2{ram_reset_n}};
 genvar i;
 generate for(i=0;i<16;i=i+1)begin:dq
  (* keep *) ODDR out(.CLK(clk),.D0(tx_first[i]),.D1(tx_second[i]),.TX(!dq_drive),.Q0(dq_out[i]),.Q1(dq_disable[i]));
  assign IO_psram_dq[i]=dq_disable[i]?1'bz:dq_out[i];
  IDDR in(.CLK(clk),.D(IO_psram_dq[i]),.Q0(q0[i]),.Q1(q1[i]));
 end
 for(i=0;i<2;i=i+1)begin:control
  (* keep *) ODDR ck(.CLK(clk_ck),.D0(clock_launch),.D1(1'b0),.TX(1'b0),.Q0(O_psram_ck[i]),.Q1());
  (* keep *) ODDR ckn(.CLK(clk_ck),.D0(!clock_launch),.D1(1'b1),.TX(1'b0),.Q0(O_psram_ck_n[i]),.Q1());
  (* keep *) ODDR cs(.CLK(clk),.D0(ram_cs_n),.D1(ram_cs_n),.TX(1'b0),.Q0(O_psram_cs_n[i]),.Q1());
  (* keep *) ODDR rwds(.CLK(clk),.D0(1'b0),.D1(1'b0),.TX(!rwds_drive),.Q0(rwds_out[i]),.Q1(rwds_disable[i]));
  assign IO_psram_rwds[i]=rwds_disable[i]?1'bz:rwds_out[i];
  IDDR strobe(.CLK(clk),.D(IO_psram_rwds[i]),.Q0(strobe0[i]),.Q1(strobe1[i]));
 end endgenerate
 reg [1:0] armed,high_pending;
 reg [7:0] high_byte[0:1];
 reg a,h,v;reg [7:0] b;reg [15:0] word_value;
 reg s;reg [7:0] byte_value;
 integer p,k;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   rx_valid<=0;rx_word0<=0;rx_word1<=0;armed<=0;high_pending<=0;
   high_byte[0]<=0;high_byte[1]<=0;fault<=0;
  end else begin
   rx_valid<=0;
   if(!rx_enable || ram_cs_n)begin armed<=0;high_pending<=0;end
   else begin
    for(p=0;p<2;p=p+1)begin
     a=armed[p];h=high_pending[p];b=high_byte[p];v=0;word_value=0;
     // Assemble at an RWDS high->low transition. The first/high byte can be
     // Q0 or the previous cycle's Q1, allowing different die clock-to-output.
     for(k=0;k<2;k=k+1)begin
      s=k==0?strobe0[p]:strobe1[p];byte_value=k==0?q0[p*8+:8]:q1[p*8+:8];
      if(!s)begin
       a=1;
       if(h)begin
        if(v)fault<=1;
        word_value={b,byte_value};v=1;h=0;
       end
      end else if(a)begin
       if(h)fault<=1; // a missing half-cycle is a fatal sampling error
       b=byte_value;h=1;
      end
     end
     armed[p]<=a;high_pending[p]<=h;high_byte[p]<=b;
     rx_valid[p]<=v;
     if(v)begin if(p==0)rx_word0<=word_value;else rx_word1<=word_value;end
    end
   end
  end
 end
endmodule
